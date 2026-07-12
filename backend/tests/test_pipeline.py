import json
from pathlib import Path

from app import db
from app.ingest import global_search, pipeline

from .pdf_helper import build_pdf
from .test_edgar import FACTS, SUBMISSIONS, TICKERS
from .test_rag import FakeEmbedder

FIXTURES = Path(__file__).parent / "fixtures"


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def test_edgar_ingest_end_to_end(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    html = (FIXTURES / "mini_10k.html").read_text(encoding="utf-8")

    def fake_fetch(conn_, url, ttl=None, binary=False):
        if "company_tickers" in url:
            return json.dumps(TICKERS)
        if "submissions" in url:
            return json.dumps(SUBMISSIONS)
        if "companyfacts" in url:
            return json.dumps(FACTS)
        if "Archives" in url:
            return html
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(pipeline.web, "fetch_url", fake_fetch)
    cid = pipeline.ingest_company(conn, "AAPL", "edgar", embedder=FakeEmbedder(),
                                  embed_model="fake")

    company = db.query(conn, "SELECT * FROM companies WHERE id=?", (cid,))[0]
    assert company["status"] == "ready"
    assert company["cik"] == "0000320193"
    assert company["ticker"] == "AAPL"

    reports = db.query(conn, "SELECT * FROM reports WHERE company_id=? ORDER BY fiscal_year DESC", (cid,))
    assert [r["fiscal_year"] for r in reports] == [2025, 2024, 2023]
    assert all(r["status"] == "ready" for r in reports)

    chunks = db.query(conn, "SELECT * FROM chunks")
    assert len(chunks) > 0
    assert all(c["embedding"] is not None for c in chunks)

    tables = db.query(conn, "SELECT * FROM doc_tables")
    assert len(tables) == 3  # one per report fixture

    facts = db.query(conn, "SELECT * FROM facts WHERE company_id=?", (cid,))
    by = {(f["metric"], f["fiscal_year"], f["source_kind"]) for f in facts}
    assert ("revenue", 2025, "xbrl") in by
    assert ("revenue_growth_yoy", 2025, "derived") in by

    # re-ingest is idempotent (no duplicate reports/facts)
    pipeline.ingest_company(conn, "AAPL", "edgar", embedder=FakeEmbedder(),
                            embed_model="fake")
    assert len(db.query(conn, "SELECT * FROM reports WHERE company_id=?", (cid,))) == 3


def test_global_ingest_end_to_end(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)

    def fake_find(conn_, company, n=3):
        return [{"year": 2025, "url": "https://acme.com/ar2025.pdf", "title": "AR 2025"},
                {"year": 2024, "url": "https://acme.com/ar2024.pdf", "title": "AR 2024"}]

    def fake_download(conn_, url):
        pdf = tmp_path / (url.rsplit("/", 1)[1])
        pdf.write_bytes(build_pdf([
            ["FINANCIAL HIGHLIGHTS", "Revenue was 1,200 for the year.",
             "RISK FACTORS", "Competition may reduce margins."]]))
        return str(pdf)

    monkeypatch.setattr(pipeline.global_search, "find_annual_reports", fake_find)
    monkeypatch.setattr(pipeline.global_search, "download_report", fake_download)

    cid = pipeline.ingest_company(conn, "Acme Global", "global",
                                  embedder=FakeEmbedder(), embed_model="fake")
    company = db.query(conn, "SELECT * FROM companies WHERE id=?", (cid,))[0]
    assert company["status"] == "ready"
    reports = db.query(conn, "SELECT * FROM reports WHERE company_id=?", (cid,))
    assert len(reports) == 2
    assert all(r["format"] == "pdf" for r in reports)
    chunks = db.query(conn, "SELECT * FROM chunks")
    assert all(c["embedding"] is not None for c in chunks)


def test_table_facts_extraction(tmp_path):
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "global"})
    rid = db.insert(conn, "reports", {"company_id": cid, "fiscal_year": 2025,
                                      "status": "ready"})
    tid = db.insert(conn, "doc_tables", {"report_id": rid, "caption": "Highlights",
        "data_json": json.dumps([["Metric", "2025", "2024"],
                                 ["Total revenue", "1,200.5", "1,071"],
                                 ["Net profit", "(240)", "200"],
                                 ["Something else", "n/a", "-"]])})
    n = pipeline.extract_table_facts(conn, cid)
    assert n >= 4
    facts = {(f["metric"], f["fiscal_year"]): f
             for f in db.query(conn, "SELECT * FROM facts WHERE company_id=?", (cid,))}
    assert facts[("revenue", 2025)]["value"] == 1200.5
    assert facts[("net_income", 2025)]["value"] == -240.0  # parens = negative
    assert facts[("revenue", 2024)]["value"] == 1071.0
    ref = json.loads(facts[("revenue", 2025)]["source_ref"])
    assert ref["table_id"] == tid


def test_ingest_failure_marks_company(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)

    def boom(conn_, url, ttl=None, binary=False):
        raise RuntimeError("network down")

    monkeypatch.setattr(pipeline.web, "fetch_url", boom)
    cid = pipeline.ingest_company(conn, "AAPL", "edgar", embedder=FakeEmbedder(),
                                  embed_model="fake")
    company = db.query(conn, "SELECT * FROM companies WHERE id=?", (cid,))[0]
    assert company["status"] == "failed"
    assert "network down" in company["error"]
