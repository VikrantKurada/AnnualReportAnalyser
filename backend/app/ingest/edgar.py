"""SEC EDGAR client: company resolution, 10-K filings, XBRL company facts.

All HTTP goes through web.fetch_url so responses are cached in SQLite.
"""
import json
import sqlite3
from datetime import date

from .. import web

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
WEEK = 7 * 86400

# priority-ordered XBRL tags per normalized metric
TAG_MAP: list[tuple[str, list[str]]] = [
    ("revenue", ["RevenueFromContractWithCustomerExcludingAssessedTax",
                 "Revenues", "SalesRevenueNet"]),
    ("net_income", ["NetIncomeLoss"]),
    ("operating_income", ["OperatingIncomeLoss"]),
    ("total_assets", ["Assets"]),
    ("total_liabilities", ["Liabilities"]),
    ("equity", ["StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    ("cash", ["CashAndCashEquivalentsAtCarryingValue"]),
    ("current_assets", ["AssetsCurrent"]),
    ("current_liabilities", ["LiabilitiesCurrent"]),
    ("long_term_debt", ["LongTermDebtNoncurrent", "LongTermDebt"]),
    ("operating_cash_flow", ["NetCashProvidedByUsedInOperatingActivities"]),
    ("eps_diluted", ["EarningsPerShareDiluted", "EarningsPerShareBasic"]),
    ("shares_outstanding", ["CommonStockSharesOutstanding"]),
]

METRIC_LABELS = {
    "revenue": "Revenue", "net_income": "Net income",
    "operating_income": "Operating income", "total_assets": "Total assets",
    "total_liabilities": "Total liabilities", "equity": "Shareholders' equity",
    "cash": "Cash & equivalents", "current_assets": "Current assets",
    "current_liabilities": "Current liabilities", "long_term_debt": "Long-term debt",
    "operating_cash_flow": "Operating cash flow", "eps_diluted": "EPS (diluted)",
    "shares_outstanding": "Shares outstanding",
}


def resolve_company(conn: sqlite3.Connection, query: str) -> dict:
    data = json.loads(web.fetch_url(conn, TICKERS_URL, ttl=WEEK))
    entries = [{"cik": f"{e['cik_str']:010d}", "ticker": e["ticker"],
                "name": e["title"]} for e in data.values()]
    q = query.strip().lower()

    match = next((e for e in entries if e["ticker"].lower() == q), None)
    candidates = [e for e in entries if q in e["name"].lower()]
    if match is None and candidates:
        match = candidates[0]
    return {"match": match, "candidates": candidates[:5]}


def list_annual_filings(conn: sqlite3.Connection, cik: str, n: int = 3) -> list[dict]:
    data = json.loads(web.fetch_url(conn, SUBMISSIONS_URL.format(cik=cik), ttl=86400))
    recent = data["filings"]["recent"]
    filings = []
    for i, form in enumerate(recent["form"]):
        if form not in ("10-K", "10-K/A"):
            continue
        accession = recent["accessionNumber"][i]
        report_date = recent["reportDate"][i]
        filings.append({
            "form": form,
            "fiscal_year": int(report_date[:4]),
            "filed_at": recent["filingDate"][i],
            "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession.replace('-', '')}/{recent['primaryDocument'][i]}"),
        })
    # prefer plain 10-K per fiscal year, newest first
    by_year: dict[int, dict] = {}
    for f in sorted(filings, key=lambda f: (f["fiscal_year"], f["form"] == "10-K")):
        by_year[f["fiscal_year"]] = f
    return sorted(by_year.values(), key=lambda f: -f["fiscal_year"])[:n]


def company_facts(conn: sqlite3.Connection, cik: str,
                  max_years: int = 4) -> list[dict]:
    """Extract normalized annual facts from the XBRL company-facts API."""
    data = json.loads(web.fetch_url(conn, FACTS_URL.format(cik=cik), ttl=86400))
    gaap = data.get("facts", {}).get("us-gaap", {})
    out: dict[tuple[str, int], dict] = {}

    for metric, tags in TAG_MAP:
        for tag in tags:
            concept = gaap.get(tag)
            if not concept:
                continue
            unit, points = _pick_unit(concept.get("units", {}))
            for dp in points:
                if dp.get("form") != "10-K" or dp.get("fp") != "FY":
                    continue
                end = dp.get("end")
                if not end:
                    continue
                if dp.get("start") and _days(dp["start"], end) < 300:
                    continue  # quarterly point mislabelled FY
                fy = int(end[:4])
                key = (metric, fy)
                if key in out:
                    continue  # higher-priority tag or earlier point already set
                out[key] = {
                    "metric": metric, "label": METRIC_LABELS.get(metric, metric),
                    "fiscal_year": fy, "value": dp.get("val"), "unit": unit,
                    "source_kind": "xbrl",
                    "source_ref": json.dumps({"tag": tag, "accn": dp.get("accn"),
                                              "end": end, "form": "10-K"}),
                }

    facts = list(out.values())
    if facts:
        years = sorted({f["fiscal_year"] for f in facts}, reverse=True)[:max_years]
        facts = [f for f in facts if f["fiscal_year"] in set(years)]
    return sorted(facts, key=lambda f: (f["metric"], -f["fiscal_year"]))


def _pick_unit(units: dict) -> tuple[str, list]:
    for preferred in ("USD", "USD/shares", "shares"):
        if preferred in units:
            return preferred, units[preferred]
    if units:
        name = next(iter(units))
        return name, units[name]
    return "", []


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days
