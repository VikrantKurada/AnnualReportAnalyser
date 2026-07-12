import json
import sqlite3
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import db as db_mod
from .. import rag
from ..analysis import analyze, valuation
from ..ingest import pipeline
from .deps import get_db

router = APIRouter()


class FetchRequest(BaseModel):
    name: str
    source_mode: str = "edgar"  # "edgar" | "global"


class SaveRequest(BaseModel):
    saved: bool


class AnalyzeRequest(BaseModel):
    persona_id: int | None = None
    session_key: str = ""


def _company_payload(conn, company_id: int) -> dict:
    rows = db_mod.query(conn, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not rows:
        raise HTTPException(404, "company not found")
    company = rows[0]
    company["reports"] = db_mod.query(conn,
        "SELECT id, fiscal_year, form, source_url, format, status, error, filed_at"
        " FROM reports WHERE company_id=? ORDER BY fiscal_year DESC", (company_id,))
    return company


@router.post("/companies/fetch")
def fetch_company(req: FetchRequest, request: Request,
                  conn: sqlite3.Connection = Depends(get_db)):
    if req.source_mode not in ("edgar", "global"):
        raise HTTPException(422, "source_mode must be 'edgar' or 'global'")
    company_id = pipeline.find_or_create_company(conn, req.name.strip(), req.source_mode)
    db_mod.update(conn, "companies", company_id, {"status": "queued", "error": None})
    db_path = request.app.state.db_path

    def work():
        bg = db_mod.get_conn(db_path)
        try:
            pipeline.ingest_company(bg, req.name.strip(), req.source_mode)
        finally:
            bg.close()

    threading.Thread(target=work, daemon=True).start()
    return _company_payload(conn, company_id)


@router.get("/companies")
def list_companies(conn: sqlite3.Connection = Depends(get_db)):
    return db_mod.query(conn,
        "SELECT c.*, (SELECT COUNT(*) FROM reports r WHERE r.company_id = c.id"
        " AND r.status = 'ready') AS ready_reports FROM companies c ORDER BY c.name")


@router.get("/companies/{company_id}")
def get_company(company_id: int, conn: sqlite3.Connection = Depends(get_db)):
    return _company_payload(conn, company_id)


@router.post("/companies/{company_id}/save")
def save_company(company_id: int, req: SaveRequest,
                 conn: sqlite3.Connection = Depends(get_db)):
    _company_payload(conn, company_id)
    db_mod.update(conn, "companies", company_id, {"saved": int(req.saved)})
    return {"ok": True, "saved": req.saved}


@router.delete("/companies/{company_id}")
def delete_company(company_id: int, conn: sqlite3.Connection = Depends(get_db)):
    _company_payload(conn, company_id)
    conn.execute("DELETE FROM companies WHERE id=?", (company_id,))
    conn.commit()
    return {"ok": True}


@router.get("/companies/{company_id}/facts")
def company_facts(company_id: int, conn: sqlite3.Connection = Depends(get_db)):
    _company_payload(conn, company_id)
    return rag.fact_context(conn, company_id)


@router.get("/companies/{company_id}/valuation")
def company_valuation(company_id: int, conn: sqlite3.Connection = Depends(get_db)):
    company = _company_payload(conn, company_id)
    if not company.get("ticker"):
        return {"available": False, "reason": "no ticker for this company"}
    try:
        quote = valuation.get_quote(conn, company["ticker"])
    except Exception as e:  # noqa: BLE001 - quote source down is not an error state
        return {"available": False, "reason": f"quote fetch failed: {e}"}
    if quote is None:
        return {"available": False,
                "reason": f"no quote found for {company['ticker']}"}
    result = valuation.compute_valuation(conn, company_id, quote)
    result["available"] = True
    result["ticker"] = company["ticker"]
    return result


@router.post("/companies/{company_id}/analyze")
def analyze_company(company_id: int, req: AnalyzeRequest, request: Request,
                    conn: sqlite3.Connection = Depends(get_db)):
    _company_payload(conn, company_id)
    db_path = request.app.state.db_path

    def work():
        bg = db_mod.get_conn(db_path)
        try:
            analyze.run_analysis(bg, company_id, req.session_key,
                                 persona_id=req.persona_id)
        except Exception as e:  # noqa: BLE001 - background job records failure
            db_mod.insert(bg, "analyses", {
                "company_id": company_id, "persona_id": req.persona_id,
                "kind": "error", "content_json": json.dumps({"error": str(e)})})
        finally:
            bg.close()

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started"}


@router.get("/companies/{company_id}/analysis")
def latest_analysis(company_id: int, persona_id: int | None = None,
                    conn: sqlite3.Connection = Depends(get_db)):
    clause = "AND persona_id IS NULL" if persona_id is None else "AND persona_id = ?"
    params: tuple = (company_id,) if persona_id is None else (company_id, persona_id)
    rows = db_mod.query(conn,
        f"SELECT * FROM analyses WHERE company_id = ? {clause}"
        " AND kind IN ('overview','error') ORDER BY id DESC LIMIT 1", params)
    if not rows:
        return {"analysis": None}
    row = rows[0]
    row["content"] = json.loads(row.pop("content_json"))
    row.pop("trace_json", None)
    return {"analysis": row}


@router.get("/trace/{kind}/{ref_id}")
def get_trace(kind: str, ref_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if kind not in ("chunk", "fact"):
        raise HTTPException(422, "kind must be 'chunk' or 'fact'")
    trace = analyze.get_trace(conn, kind, ref_id)
    if trace is None:
        raise HTTPException(404, "trace not found")
    return trace
