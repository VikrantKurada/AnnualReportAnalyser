import json

from app import db
from app.ingest import edgar

TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
}

SUBMISSIONS = {
    "cik": "320193",
    "name": "Apple Inc.",
    "filings": {"recent": {
        "form": ["10-Q", "10-K", "8-K", "10-K", "10-K", "10-K"],
        "accessionNumber": ["0000-25-1", "0000320193-25-000123", "0000-25-2",
                            "0000320193-24-000123", "0000320193-23-000106",
                            "0000320193-22-000108"],
        "primaryDocument": ["q.htm", "aapl-20250927.htm", "k.htm",
                            "aapl-20240928.htm", "aapl-20230930.htm",
                            "aapl-20220924.htm"],
        "reportDate": ["2025-06-28", "2025-09-27", "2025-10-01",
                       "2024-09-28", "2023-09-30", "2022-09-24"],
        "filingDate": ["2025-07-30", "2025-11-01", "2025-10-02",
                       "2024-11-01", "2023-11-03", "2022-10-28"],
    }},
}

FACTS = {"facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 400000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 391000, "accn": "a1",
         "start": "2023-10-01", "end": "2024-09-28"},
        # quarterly datapoint mislabelled FY must be excluded (short duration)
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 94900, "accn": "a1",
         "start": "2025-06-29", "end": "2025-09-27"},
    ]}},
    "Revenues": {"units": {"USD": [
        # lower priority tag for same year must not override
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 999999, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
        {"fy": 2023, "fp": "FY", "form": "10-K", "val": 383000, "accn": "a0",
         "start": "2022-09-25", "end": "2023-09-30"},
    ]}},
    "Assets": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 365000, "accn": "a1",
         "end": "2025-09-27"},
        {"fy": 2025, "fp": "FY", "form": "10-Q", "val": 1, "accn": "aq",
         "end": "2025-06-28"},
    ]}},
    "EarningsPerShareDiluted": {"units": {"USD/shares": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 7.1, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "GrossProfit": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 190000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "ResearchAndDevelopmentExpense": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 32000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 11000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "PaymentsForRepurchaseOfCommonStock": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 95000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "IncomeTaxExpenseBenefit": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 21000, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
    "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 15100, "accn": "a1",
         "start": "2024-09-29", "end": "2025-09-27"},
    ]}},
}}}


# GSK-like foreign private issuer: 20-F filings, ifrs-full taxonomy, GBP.
FPI_SUBMISSIONS = {
    "cik": "1131399",
    "name": "GSK plc",
    "filings": {"recent": {
        "form": ["6-K", "20-F", "20-F", "20-F", "20-F/A", "20-F"],
        "accessionNumber": ["0000-25-9", "0001131399-26-000010",
                            "0001131399-25-000010", "0001131399-24-000010",
                            "0001131399-23-000099", "0001131399-23-000010"],
        "primaryDocument": ["k.htm", "gsk-20251231.htm", "gsk-20241231.htm",
                            "gsk-20231231.htm", "d495695d20fa.htm",
                            "d382677d20f.htm"],
        "reportDate": ["2025-06-30", "2025-12-31", "2024-12-31",
                       "2023-12-31", "2022-12-31", "2022-12-31"],
        "filingDate": ["2025-07-30", "2026-02-20", "2025-02-20",
                       "2024-02-20", "2023-08-01", "2023-02-20"],
    }},
}

FPI_FACTS = {"facts": {
    "ifrs-full": {
        "Revenue": {"units": {"GBP": [
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 32667000000,
             "accn": "g1", "start": "2025-01-01", "end": "2025-12-31"},
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 31376000000,
             "accn": "g1", "start": "2024-01-01", "end": "2024-12-31"},
        ]}},
        "ProfitLoss": {"units": {"GBP": [
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 6000000000,
             "accn": "g1", "start": "2025-01-01", "end": "2025-12-31"},
        ]}},
        "ProfitLossAttributableToOwnersOfParent": {"units": {"GBP": [
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 5600000000,
             "accn": "g1", "start": "2025-01-01", "end": "2025-12-31"},
        ]}},
        "DilutedEarningsLossPerShare": {"units": {"GBP/shares": [
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 1.35,
             "accn": "g1", "start": "2025-01-01", "end": "2025-12-31"},
        ]}},
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities":
            {"units": {"GBP": [
                {"fy": 2025, "fp": "FY", "form": "20-F", "val": 1200000000,
                 "accn": "g1", "start": "2025-01-01", "end": "2025-12-31"},
            ]}},
        # quarterly 6-K datapoint must be excluded
        "Assets": {"units": {"GBP": [
            {"fy": 2025, "fp": "FY", "form": "20-F", "val": 90000000000,
             "accn": "g1", "end": "2025-12-31"},
            {"fy": 2025, "fp": "Q2", "form": "6-K", "val": 1,
             "accn": "g9", "end": "2025-06-30"},
        ]}},
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"fy": 2025, "fp": "FY", "form": "20-F", "val": 4100000000,
         "accn": "g1", "end": "2025-12-31"},
    ]}}},
}}


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def fake_fetch(responses):
    def _fetch(conn, url, ttl=None, binary=False):
        for frag, payload in responses.items():
            if frag in url:
                return json.dumps(payload)
        raise AssertionError(f"unexpected url {url}")
    return _fetch


def test_resolve_by_ticker(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"company_tickers": TICKERS}))
    r = edgar.resolve_company(conn, "aapl")
    assert r["match"]["cik"] == "0000320193"
    assert r["match"]["name"] == "Apple Inc."


def test_resolve_by_name_substring(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"company_tickers": TICKERS}))
    r = edgar.resolve_company(conn, "tesla")
    assert r["match"]["ticker"] == "TSLA"
    r2 = edgar.resolve_company(conn, "zzz nonexistent")
    assert r2["match"] is None


def test_list_annual_filings(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"submissions": SUBMISSIONS}))
    filings = edgar.list_annual_filings(conn, "0000320193", n=3)
    assert [f["fiscal_year"] for f in filings] == [2025, 2024, 2023]
    assert filings[0]["url"] == ("https://www.sec.gov/Archives/edgar/data/320193/"
                                 "000032019325000123/aapl-20250927.htm")
    assert filings[0]["form"] == "10-K"


def test_company_facts_mapping(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"companyfacts": FACTS}))
    facts = edgar.company_facts(conn, "0000320193")
    by = {(f["metric"], f["fiscal_year"]): f for f in facts}

    assert by[("revenue", 2025)]["value"] == 400000  # priority tag wins
    assert by[("revenue", 2024)]["value"] == 391000  # prior year from same filing
    assert by[("revenue", 2023)]["value"] == 383000  # fallback tag fills gap
    assert ("revenue", 2026) not in by
    assert by[("total_assets", 2025)]["value"] == 365000  # 10-Q point excluded
    assert by[("eps_diluted", 2025)]["value"] == 7.1
    ref = json.loads(by[("revenue", 2025)]["source_ref"])
    assert ref["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert by[("revenue", 2025)]["source_kind"] == "xbrl"


def test_list_annual_filings_accepts_20f(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"submissions": FPI_SUBMISSIONS}))
    filings = edgar.list_annual_filings(conn, "0001131399", n=3)
    assert [f["fiscal_year"] for f in filings] == [2025, 2024, 2023]
    assert all(f["form"] == "20-F" for f in filings)
    assert filings[0]["url"].endswith("gsk-20251231.htm")

    # for FY2022 both 20-F/A and 20-F exist: the unamended one wins
    four = edgar.list_annual_filings(conn, "0001131399", n=4)
    fy2022 = next(f for f in four if f["fiscal_year"] == 2022)
    assert fy2022["form"] == "20-F"
    assert fy2022["url"].endswith("d382677d20f.htm")


def test_company_facts_ifrs_taxonomy(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"companyfacts": FPI_FACTS}))
    facts = edgar.company_facts(conn, "0001131399")
    by = {(f["metric"], f["fiscal_year"]): f for f in facts}

    assert by[("revenue", 2025)]["value"] == 32667000000
    assert by[("revenue", 2025)]["unit"] == "GBP"
    assert by[("revenue", 2024)]["value"] == 31376000000  # comparative period
    # owners-of-parent takes priority over total ProfitLoss
    assert by[("net_income", 2025)]["value"] == 5600000000
    assert by[("eps_diluted", 2025)]["value"] == 1.35
    assert by[("capex", 2025)]["value"] == 1200000000
    assert by[("total_assets", 2025)]["value"] == 90000000000  # 6-K point excluded
    assert by[("shares_outstanding", 2025)]["value"] == 4100000000  # from dei

    ref = json.loads(by[("revenue", 2025)]["source_ref"])
    assert ref["taxonomy"] == "ifrs-full"
    assert ref["tag"] == "Revenue"
    assert ref["form"] == "20-F"


def test_company_facts_analyst_metrics(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(edgar.web, "fetch_url", fake_fetch({"companyfacts": FACTS}))
    facts = edgar.company_facts(conn, "0000320193")
    by = {(f["metric"], f["fiscal_year"]): f for f in facts}

    assert by[("gross_profit", 2025)]["value"] == 190000
    assert by[("rnd_expense", 2025)]["value"] == 32000
    assert by[("capex", 2025)]["value"] == 11000
    assert by[("buybacks", 2025)]["value"] == 95000
    assert by[("income_tax", 2025)]["value"] == 21000
    assert by[("shares_diluted_wa", 2025)]["value"] == 15100
    assert by[("shares_diluted_wa", 2025)]["unit"] == "shares"
