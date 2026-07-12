import pytest

from app import db
from app.analysis import valuation

import json

# 1783713601 = 2026-07-10 (UTC)
YAHOO_JSON = json.dumps({"chart": {"result": [{"meta": {
    "regularMarketPrice": 252.5, "regularMarketTime": 1783713601,
    "currency": "USD"}}], "error": None}})

YAHOO_EMPTY = json.dumps({"chart": {"result": None,
                                    "error": {"code": "Not Found"}}})


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def test_get_quote_parses_yahoo(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(valuation.web, "fetch_url",
                        lambda conn_, url, ttl=None, binary=False: YAHOO_JSON)
    q = valuation.get_quote(conn, "AAPL")
    assert q["price"] == 252.5
    assert q["asof"] == "2026-07-10"
    assert q["currency"] == "USD"
    assert "finance.yahoo.com" in q["source_url"]


def test_get_quote_handles_unknown_ticker(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(valuation.web, "fetch_url",
                        lambda conn_, url, ttl=None, binary=False: YAHOO_EMPTY)
    assert valuation.get_quote(conn, "ZZZZ") is None


def seed_facts(conn):
    cid = db.insert(conn, "companies", {"name": "Acme", "ticker": "ACME",
                                        "source_mode": "edgar", "status": "ready"})
    ids = {}
    rows = [
        ("revenue", 1000.0), ("net_income", 200.0), ("equity", 500.0),
        ("eps_diluted", 2.0), ("shares_outstanding", 100.0),
        ("ebitda", 350.0), ("net_debt", 550.0), ("fcf", 200.0),
        ("dividends_paid", 40.0), ("buybacks", 60.0),
    ]
    for metric, value in rows:
        ids[metric] = db.insert(conn, "facts", {
            "company_id": cid, "fiscal_year": 2025, "metric": metric,
            "value": value, "source_kind": "xbrl"})
    return cid, ids


def test_compute_valuation(tmp_path):
    conn = make_conn(tmp_path)
    cid, ids = seed_facts(conn)
    quote = {"price": 50.0, "asof": "2026-07-10", "source_url": "https://stooq.com/x"}
    v = valuation.compute_valuation(conn, cid, quote)

    m = {row["metric"]: row for row in v["metrics"]}
    assert m["market_cap"]["value"] == pytest.approx(5000.0)  # 50 × 100 shares
    assert m["pe"]["value"] == pytest.approx(25.0)            # 50 / 2 eps
    assert m["ps"]["value"] == pytest.approx(5.0)             # 5000 / 1000
    assert m["pb"]["value"] == pytest.approx(10.0)            # 5000 / 500
    assert m["ev"]["value"] == pytest.approx(5550.0)          # mcap + net debt
    assert m["ev_ebitda"]["value"] == pytest.approx(5550 / 350)
    assert m["fcf_yield"]["value"] == pytest.approx(200 / 5000)
    assert m["dividend_yield"]["value"] == pytest.approx(40 / 5000)
    assert m["buyback_yield"]["value"] == pytest.approx(60 / 5000)
    assert ids["revenue"] in m["ps"]["inputs"]
    assert "formula" in m["pe"]
    assert v["price"] == 50.0
    assert v["fiscal_year"] == 2025


def test_compute_valuation_currency_mismatch_blocks_multiples(tmp_path):
    """GBP filings (ADR) + USD quote must not produce cross-currency multiples."""
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "GSK plc", "ticker": "GSK",
                                        "source_mode": "edgar", "status": "ready"})
    for metric, value in [("revenue", 32667000000.0), ("eps_diluted", 1.35),
                          ("shares_outstanding", 4100000000.0)]:
        db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                                  "metric": metric, "value": value,
                                  "unit": "GBP" if metric != "shares_outstanding" else "shares",
                                  "source_kind": "xbrl"})
    quote = {"price": 40.0, "asof": "2026-07-10", "currency": "USD",
             "source_url": "u"}
    v = valuation.compute_valuation(conn, cid, quote)
    assert v["currency_mismatch"] is True
    assert v["filing_currency"] == "GBP"
    assert v["metrics"] == []


def test_compute_valuation_matching_currency_ok(tmp_path):
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "ticker": "ACME",
                                        "source_mode": "edgar", "status": "ready"})
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "eps_diluted", "value": 2.0, "unit": "USD/shares",
                              "source_kind": "xbrl"})
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "revenue", "value": 100.0, "unit": "USD",
                              "source_kind": "xbrl"})
    quote = {"price": 50.0, "asof": "2026-07-10", "currency": "USD",
             "source_url": "u"}
    v = valuation.compute_valuation(conn, cid, quote)
    assert v.get("currency_mismatch") is False
    assert any(m["metric"] == "pe" for m in v["metrics"])


def test_compute_valuation_missing_facts(tmp_path):
    conn = make_conn(tmp_path)
    cid = db.insert(conn, "companies", {"name": "Bare", "ticker": "BARE",
                                        "source_mode": "edgar"})
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "revenue", "value": 10.0,
                              "source_kind": "xbrl"})
    v = valuation.compute_valuation(conn, cid,
        {"price": 5.0, "asof": "2026-07-10", "source_url": "u"})
    metrics = {row["metric"] for row in v["metrics"]}
    # no shares -> no market cap or mcap-derived multiples
    assert "market_cap" not in metrics
    assert "ps" not in metrics
