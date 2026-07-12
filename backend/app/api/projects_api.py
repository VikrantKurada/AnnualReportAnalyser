import json
import sqlite3
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import db as db_mod
from .. import projects as projects_mod
from .deps import get_db

router = APIRouter()


class ProjectRequest(BaseModel):
    name: str
    description: str = ""


class CompanyRef(BaseModel):
    company_id: int


class MetricRequest(BaseModel):
    name: str
    description: str = ""
    formula: str


class SuggestRequest(BaseModel):
    prompt: str
    session_key: str = ""


class AnalyzeRequest(BaseModel):
    persona_id: int | None = None
    session_key: str = ""


@router.post("/projects")
def create_project(req: ProjectRequest, conn: sqlite3.Connection = Depends(get_db)):
    pid = db_mod.insert(conn, "projects", {"name": req.name,
                                           "description": req.description})
    return db_mod.query(conn, "SELECT * FROM projects WHERE id=?", (pid,))[0]


@router.get("/projects")
def list_projects(conn: sqlite3.Connection = Depends(get_db)):
    return db_mod.query(conn,
        "SELECT p.*, (SELECT COUNT(*) FROM project_companies pc"
        " WHERE pc.project_id = p.id) AS company_count FROM projects p ORDER BY p.id DESC")


@router.get("/projects/{project_id}")
def get_project(project_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = db_mod.query(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
    if not rows:
        raise HTTPException(404, "project not found")
    project = rows[0]
    project["companies"] = db_mod.query(conn,
        "SELECT c.id, c.name, c.ticker, c.status FROM project_companies pc"
        " JOIN companies c ON c.id = pc.company_id WHERE pc.project_id=?", (project_id,))
    project["metrics"] = _metrics(conn, project_id)
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/companies")
def add_company(project_id: int, req: CompanyRef,
                conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("INSERT OR IGNORE INTO project_companies (project_id, company_id)"
                 " VALUES (?, ?)", (project_id, req.company_id))
    conn.commit()
    return {"ok": True}


@router.delete("/projects/{project_id}/companies/{company_id}")
def remove_company(project_id: int, company_id: int,
                   conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM project_companies WHERE project_id=? AND company_id=?",
                 (project_id, company_id))
    conn.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/compare")
def compare(project_id: int, conn: sqlite3.Connection = Depends(get_db)):
    return projects_mod.compare(conn, project_id)


def _metrics(conn, project_id: int) -> list[dict]:
    rows = db_mod.query(conn,
        "SELECT * FROM project_metrics WHERE project_id=? ORDER BY id DESC",
        (project_id,))
    for r in rows:
        r["results"] = json.loads(r.pop("results_json") or "{}")
        r["trace"] = json.loads(r.pop("trace_json") or "{}")
    return rows


@router.post("/projects/{project_id}/metrics")
def add_metric(project_id: int, req: MetricRequest,
               conn: sqlite3.Connection = Depends(get_db)):
    try:
        projects_mod.add_custom_metric(conn, project_id, req.name,
                                       req.description, req.formula)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _metrics(conn, project_id)


@router.delete("/projects/{project_id}/metrics/{metric_id}")
def delete_metric(project_id: int, metric_id: int,
                  conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM project_metrics WHERE id=? AND project_id=?",
                 (metric_id, project_id))
    conn.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/metrics/suggest")
def suggest_metric(project_id: int, req: SuggestRequest,
                   conn: sqlite3.Connection = Depends(get_db)):
    try:
        return projects_mod.suggest_metric(conn, project_id, req.prompt,
                                           session_key=req.session_key)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/projects/{project_id}/analyze")
def analyze_project(project_id: int, req: AnalyzeRequest, request: Request,
                    conn: sqlite3.Connection = Depends(get_db)):
    db_path = request.app.state.db_path

    def work():
        bg = db_mod.get_conn(db_path)
        try:
            projects_mod.run_project_analysis(bg, project_id, req.session_key,
                                              persona_id=req.persona_id)
        except Exception as e:  # noqa: BLE001
            db_mod.insert(bg, "analyses", {
                "project_id": project_id, "kind": "error",
                "content_json": json.dumps({"error": str(e)})})
        finally:
            bg.close()

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started"}


@router.get("/projects/{project_id}/analysis")
def latest_analysis(project_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = db_mod.query(conn,
        "SELECT * FROM analyses WHERE project_id = ?"
        " AND kind IN ('comparison','error') ORDER BY id DESC LIMIT 1", (project_id,))
    if not rows:
        return {"analysis": None}
    row = rows[0]
    row["content"] = json.loads(row.pop("content_json"))
    return {"analysis": row}
