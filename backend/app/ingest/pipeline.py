"""Ingestion orchestrator: fetch → parse → store → embed → facts.

Both source modes converge here; company/report status rows drive UI progress
(new → ingesting → ready|failed per company, pending → fetching → parsing →
embedding → ready|failed per report).
"""
import json
import re
import sqlite3

from .. import db, rag, web
from ..analysis import metrics
from . import chunking, edgar, global_search, parse_html, parse_pdf

TABLE_METRIC_SYNONYMS = {
    "revenue": ["total revenue", "revenue from operations", "revenue", "total income", "net sales", "sales"],
    "gross_profit": ["gross profit"],
    "net_income": ["net income", "net profit", "profit for the year", "profit after tax"],
    "operating_income": ["operating income", "operating profit"],
    "ebitda": ["ebitda"],
    "total_assets": ["total assets"],
    "total_liabilities": ["total liabilities"],
    "equity": ["total equity", "shareholders' equity", "shareholders equity",
               "stockholders equity"],
    "cash": ["cash and cash equivalents"],
    "operating_cash_flow": ["cash generated from operations",
                            "net cash from operating activities",
                            "net cash provided by operating activities"],
}

YEAR_RE = re.compile(r"^(?:FY\s*)?(20\d\d)$", re.IGNORECASE)
NUM_RE = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?$")


def find_or_create_company(conn: sqlite3.Connection, name: str,
                           source_mode: str) -> int:
    row = conn.execute(
        "SELECT id FROM companies WHERE (lower(name) = lower(?) OR lower(ticker) = lower(?))"
        " AND source_mode = ?", (name, name, source_mode)).fetchone()
    if row:
        return row["id"]
    return db.insert(conn, "companies", {"name": name, "source_mode": source_mode,
                                         "status": "queued"})


def ingest_company(conn: sqlite3.Connection, name: str, source_mode: str,
                   embedder=None, embed_model: str = "") -> int:
    company_id = find_or_create_company(conn, name, source_mode)

    if embedder is None:
        from ..providers import registry
        from .. import settings as settings_mod
        embedder = registry.get_embedder(conn)
        embed_model = settings_mod.get_setting(conn, "embed_model")

    db.update(conn, "companies", company_id, {"status": "ingesting", "error": None})
    # idempotent re-ingest: wipe previous derived data for this company
    conn.execute("DELETE FROM reports WHERE company_id = ?", (company_id,))
    conn.execute("DELETE FROM facts WHERE company_id = ?", (company_id,))
    conn.commit()

    try:
        if source_mode == "edgar":
            _ingest_edgar(conn, company_id, name, embedder, embed_model)
        else:
            _ingest_global(conn, company_id, name, embedder, embed_model)
        _store_derived_ratios(conn, company_id)
        db.update(conn, "companies", company_id, {"status": "ready"})
    except Exception as e:  # noqa: BLE001 - background job must record, not crash
        db.update(conn, "companies", company_id,
                  {"status": "failed", "error": str(e)})
    return company_id


def _ingest_edgar(conn, company_id, name, embedder, embed_model):
    resolved = edgar.resolve_company(conn, name)
    match = resolved["match"]
    if match is None:
        raise ValueError(f"no EDGAR match for {name!r}")
    db.update(conn, "companies", company_id,
              {"name": match["name"], "ticker": match["ticker"], "cik": match["cik"]})

    for filing in edgar.list_annual_filings(conn, match["cik"], n=3):
        report_id = db.insert(conn, "reports", {
            "company_id": company_id, "fiscal_year": filing["fiscal_year"],
            "form": filing["form"], "source_url": filing["url"],
            "format": "html", "status": "fetching", "filed_at": filing["filed_at"]})
        try:
            html = web.fetch_url(conn, filing["url"], ttl=0)
            db.update(conn, "reports", report_id, {"status": "parsing"})
            _store_parsed(conn, report_id, parse_html.parse(html))
            db.update(conn, "reports", report_id, {"status": "embedding"})
            rag.embed_chunks(conn, report_id, embedder, model_name=embed_model)
            db.update(conn, "reports", report_id, {"status": "ready"})
        except Exception as e:  # noqa: BLE001
            db.update(conn, "reports", report_id,
                      {"status": "failed", "error": str(e)})

    for fact in edgar.company_facts(conn, match["cik"]):
        _upsert_fact(conn, company_id, fact)


def _ingest_global(conn, company_id, name, embedder, embed_model):
    found = global_search.find_annual_reports(conn, name, n=3)
    if not found:
        raise ValueError(f"no annual reports found on the web for {name!r}")

    for item in found:
        report_id = db.insert(conn, "reports", {
            "company_id": company_id, "fiscal_year": item["year"],
            "form": "annual-report", "source_url": item["url"],
            "format": "pdf", "status": "fetching"})
        try:
            path = global_search.download_report(conn, item["url"])
            db.update(conn, "reports", report_id,
                      {"status": "parsing", "local_path": path})
            _store_parsed(conn, report_id, parse_pdf.parse(path))
            db.update(conn, "reports", report_id, {"status": "embedding"})
            rag.embed_chunks(conn, report_id, embedder, model_name=embed_model)
            db.update(conn, "reports", report_id, {"status": "ready"})
        except Exception as e:  # noqa: BLE001
            db.update(conn, "reports", report_id,
                      {"status": "failed", "error": str(e)})

    extract_table_facts(conn, company_id)


def _store_parsed(conn, report_id, doc):
    for chunk in chunking.chunk_sections(doc.sections):
        db.insert(conn, "chunks", {"report_id": report_id, **chunk})
    for table in doc.tables:
        db.insert(conn, "doc_tables", {
            "report_id": report_id, "section": table.get("section"),
            "page": table.get("page"), "caption": table.get("caption"),
            "data_json": json.dumps(table["rows"])})


def _upsert_fact(conn, company_id, fact: dict):
    conn.execute(
        "INSERT INTO facts (company_id, report_id, fiscal_year, metric, label,"
        " value, unit, source_kind, source_ref) VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(company_id, fiscal_year, metric, source_kind) DO UPDATE SET"
        " value=excluded.value, unit=excluded.unit, source_ref=excluded.source_ref,"
        " label=excluded.label",
        (company_id, fact.get("report_id"), fact["fiscal_year"], fact["metric"],
         fact.get("label"), fact.get("value"), fact.get("unit"),
         fact["source_kind"], fact.get("source_ref")))
    conn.commit()


def extract_table_facts(conn: sqlite3.Connection, company_id: int) -> int:
    """Fallback for PDF reports: mine extracted tables for known metrics."""
    tables = db.query(conn,
        "SELECT t.id, t.data_json FROM doc_tables t JOIN reports r ON r.id = t.report_id"
        " WHERE r.company_id = ?", (company_id,))
    count = 0
    for table in tables:
        rows = json.loads(table["data_json"])
        if not rows:
            continue
        year_cols = {i: int(m.group(1)) for i, cell in enumerate(rows[0])
                     if (m := YEAR_RE.match(str(cell).strip()))}
        if not year_cols:
            continue
        for ri, row in enumerate(rows[1:], 1):
            metric = _match_metric(str(row[0]) if row else "")
            if metric is None:
                continue
            for ci, year in year_cols.items():
                if ci >= len(row):
                    continue
                value = _parse_number(str(row[ci]))
                if value is None:
                    continue
                _upsert_fact(conn, company_id, {
                    "fiscal_year": year, "metric": metric,
                    "label": edgar.METRIC_LABELS.get(metric, metric),
                    "value": value, "unit": "", "source_kind": "table",
                    "source_ref": json.dumps({"table_id": table["id"],
                                              "row": ri, "col": ci})})
                count += 1
    return count


def _match_metric(cell: str) -> str | None:
    label = cell.strip().lower()
    if not label:
        return None
    for metric, synonyms in TABLE_METRIC_SYNONYMS.items():
        if any(label == s or label.startswith(s) for s in synonyms):
            return metric
    return None


def _parse_number(cell: str) -> float | None:
    cell = cell.strip().replace("$", "").replace("€", "").replace("₹", "")
    if not NUM_RE.match(cell):
        return None
    negative = cell.startswith("(") and cell.endswith(")")
    cell = cell.strip("()").replace(",", "")
    try:
        value = float(cell)
    except ValueError:
        return None
    return -value if negative else value


def _store_derived_ratios(conn, company_id):
    facts = db.query(conn,
        "SELECT id, metric, fiscal_year, value FROM facts"
        " WHERE company_id = ? AND source_kind != 'derived'", (company_id,))
    for ratio in metrics.compute_ratios(facts):
        _upsert_fact(conn, company_id, {
            "fiscal_year": ratio["fiscal_year"], "metric": ratio["metric"],
            "label": metrics.RATIO_LABELS.get(ratio["metric"], ratio["metric"]),
            "value": ratio["value"], "unit": "ratio", "source_kind": "derived",
            "source_ref": json.dumps({"formula": ratio["formula"],
                                      "inputs": ratio["inputs"]})})
