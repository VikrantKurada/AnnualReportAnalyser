from app import db


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "test.db")
    db.init_db(conn)
    return conn


def test_init_db_idempotent(tmp_path):
    conn = make_conn(tmp_path)
    db.init_db(conn)  # second run must not raise
    tables = {r["name"] for r in db.query(conn, "SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {
        "companies", "reports", "chunks", "doc_tables", "facts", "analyses",
        "personas", "projects", "project_companies", "project_metrics",
        "chat_sessions", "chat_messages", "web_cache", "settings",
        "token_usage", "mcp_servers",
    }
    assert expected <= tables


def test_insert_and_query_roundtrip(tmp_path):
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Acme Corp", "ticker": "ACME", "source_mode": "edgar"})
    assert isinstance(cid, int) and cid > 0
    rows = db.query(conn, "SELECT * FROM companies WHERE id = ?", (cid,))
    assert len(rows) == 1
    assert rows[0]["name"] == "Acme Corp"
    assert rows[0]["saved"] == 0


def test_cascade_delete_company_removes_reports_and_chunks(tmp_path):
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar"})
    rid = db.insert(conn, "reports", {"company_id": cid, "fiscal_year": 2025, "status": "ready"})
    db.insert(conn, "chunks", {"report_id": rid, "section": "Risk Factors", "seq": 0, "text": "hello"})
    conn.execute("DELETE FROM companies WHERE id = ?", (cid,))
    conn.commit()
    assert db.query(conn, "SELECT * FROM reports") == []
    assert db.query(conn, "SELECT * FROM chunks") == []


def test_facts_unique_constraint(tmp_path):
    import sqlite3

    import pytest

    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar"})
    row = {"company_id": cid, "fiscal_year": 2025, "metric": "revenue",
           "value": 100.0, "source_kind": "xbrl"}
    db.insert(conn, "facts", row)
    with pytest.raises(sqlite3.IntegrityError):
        db.insert(conn, "facts", row)
