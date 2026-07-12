import json

import pytest

from app import db, projects
from app.providers.base import ChatResult

from .test_analyze import FakeLLM


def seed(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    ids = {}
    for name, rev, ni in [("Acme", 1000.0, 200.0), ("Globex", 2000.0, 100.0)]:
        cid = db.insert(conn, "companies", {"name": name, "source_mode": "edgar",
                                            "status": "ready", "saved": 1})
        for fy, factor in [(2025, 1.0), (2024, 0.8)]:
            db.insert(conn, "facts", {"company_id": cid, "fiscal_year": fy,
                                      "metric": "revenue", "label": "Revenue",
                                      "value": rev * factor, "source_kind": "xbrl"})
            db.insert(conn, "facts", {"company_id": cid, "fiscal_year": fy,
                                      "metric": "net_income", "label": "Net income",
                                      "value": ni * factor, "source_kind": "xbrl"})
        ids[name] = cid
    pid = db.insert(conn, "projects", {"name": "Widgets war"})
    for cid in ids.values():
        db.insert(conn, "project_companies", {"project_id": pid, "company_id": cid})
    return conn, pid, ids


def test_compare_aligns_metrics(tmp_path):
    conn, pid, ids = seed(tmp_path)
    cmp_ = projects.compare(conn, pid)
    assert [c["name"] for c in cmp_["companies"]] == ["Acme", "Globex"]
    revenue_row = next(r for r in cmp_["rows"] if r["metric"] == "revenue")
    assert revenue_row["values"][str(ids["Acme"])]["2025"] == 1000.0
    assert revenue_row["values"][str(ids["Globex"])]["2025"] == 2000.0
    assert 2025 in cmp_["years"] and 2024 in cmp_["years"]


def test_custom_metric_computed_per_company(tmp_path):
    conn, pid, ids = seed(tmp_path)
    metric_id = projects.add_custom_metric(
        conn, pid, "NI ratio", "net income over revenue", "net_income / revenue")
    row = db.query(conn, "SELECT * FROM project_metrics WHERE id=?", (metric_id,))[0]
    results = json.loads(row["results_json"])
    assert results[str(ids["Acme"])]["value"] == pytest.approx(0.2)
    assert results[str(ids["Globex"])]["value"] == pytest.approx(0.05)
    assert results[str(ids["Acme"])]["fiscal_year"] == 2025
    trace = json.loads(row["trace_json"])
    assert set(trace[str(ids["Acme"])]["inputs"].keys()) == {"net_income", "revenue"}


def test_custom_metric_rejects_bad_formula(tmp_path):
    conn, pid, ids = seed(tmp_path)
    with pytest.raises(ValueError):
        projects.add_custom_metric(conn, pid, "Evil", "", "__import__('os')")
    with pytest.raises(ValueError, match="unknown variable"):
        projects.add_custom_metric(conn, pid, "Missing", "", "revenue / ebitda")


def test_suggest_metric_validates_llm_output(tmp_path):
    conn, pid, ids = seed(tmp_path)
    llm = FakeLLM([ChatResult(content=json.dumps({
        "name": "Profitability", "description": "NI margin",
        "formula": "net_income / revenue"}))])
    suggestion = projects.suggest_metric(conn, pid, "how profitable?", llm=llm)
    assert suggestion["formula"] == "net_income / revenue"
    # available metric names were given to the model
    assert "net_income" in json.dumps(llm.calls[0]["messages"])


def test_run_project_analysis_stored(tmp_path):
    conn, pid, ids = seed(tmp_path)
    llm = FakeLLM([ChatResult(content=json.dumps({
        "summary": "Acme is more profitable.",
        "comparison": [{"statement": "Acme margin higher", "citations": []}],
        "verdict": "Acme"}))])
    aid = projects.run_project_analysis(conn, pid, "sess", llm=llm)
    row = db.query(conn, "SELECT * FROM analyses WHERE id=?", (aid,))[0]
    assert row["project_id"] == pid
    assert row["kind"] == "comparison"
    assert "Acme" in row["content_json"]
