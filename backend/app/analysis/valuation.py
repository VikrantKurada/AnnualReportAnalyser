"""Market-data valuation multiples, computed on request (never stored as facts,
since prices move daily). Quotes come from Yahoo Finance's public chart API
through the shared web cache; every metric keeps the formula + fact-id + price
provenance.
"""
import json
import sqlite3
from datetime import datetime, timezone

from .. import db, web

QUOTE_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
             "{symbol}?range=1d&interval=1d")
QUOTE_TTL = 6 * 3600


def get_quote(conn: sqlite3.Connection, ticker: str) -> dict | None:
    url = QUOTE_URL.format(symbol=ticker.upper())
    data = json.loads(web.fetch_url(conn, url, ttl=QUOTE_TTL))
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        return None
    meta = results[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        return None
    asof = ""
    if meta.get("regularMarketTime"):
        asof = datetime.fromtimestamp(meta["regularMarketTime"],
                                      tz=timezone.utc).date().isoformat()
    return {"price": float(price), "asof": asof,
            "currency": meta.get("currency", ""), "source_url": url}


def compute_valuation(conn: sqlite3.Connection, company_id: int,
                      quote: dict) -> dict:
    """Latest-fiscal-year multiples. Metrics whose inputs are missing are
    simply absent."""
    rows = db.query(conn,
        "SELECT id, metric, fiscal_year, value, unit FROM facts"
        " WHERE company_id = ? AND value IS NOT NULL ORDER BY fiscal_year DESC",
        (company_id,))
    price = quote["price"]
    quote_currency = quote.get("currency", "")
    result = {"price": price, "asof": quote["asof"],
              "source_url": quote["source_url"], "fiscal_year": None,
              "quote_currency": quote_currency, "filing_currency": "",
              "currency_mismatch": False, "metrics": []}
    if not rows:
        return result

    latest = rows[0]["fiscal_year"]
    result["fiscal_year"] = latest
    facts = {r["metric"]: r for r in rows if r["fiscal_year"] == latest}

    # ADR guard: a USD quote against e.g. GBP filings would make every multiple
    # meaningless (and the ADS ratio would skew share counts on top).
    filing_currency = next(
        (r["unit"] for r in facts.values()
         if r["unit"] and len(r["unit"]) == 3 and r["unit"].isalpha()), "")
    result["filing_currency"] = filing_currency
    if (quote_currency and filing_currency
            and quote_currency.upper() != filing_currency.upper()):
        result["currency_mismatch"] = True
        return result

    def add(metric, value, formula, inputs):
        result["metrics"].append({"metric": metric, "value": value,
                                  "formula": formula,
                                  "inputs": [f["id"] for f in inputs]})

    shares = facts.get("shares_outstanding") or facts.get("shares_diluted_wa")
    eps = facts.get("eps_diluted") or facts.get("eps_basic")
    if eps and eps["value"]:
        add("pe", price / eps["value"], "price / eps_diluted", [eps])

    mcap = None
    if shares and shares["value"]:
        mcap = price * shares["value"]
        add("market_cap", mcap, f"price × {shares['metric']}", [shares])

    if mcap:
        for metric, base, formula in [("ps", "revenue", "market_cap / revenue"),
                                      ("pb", "equity", "market_cap / equity")]:
            f = facts.get(base)
            if f and f["value"]:
                add(metric, mcap / f["value"], formula, [shares, f])
        for metric, base, formula in [
                ("fcf_yield", "fcf", "fcf / market_cap"),
                ("dividend_yield", "dividends_paid", "dividends_paid / market_cap"),
                ("buyback_yield", "buybacks", "buybacks / market_cap")]:
            f = facts.get(base)
            if f is not None:
                add(metric, f["value"] / mcap, formula, [f, shares])

        net_debt = facts.get("net_debt")
        ev = mcap + net_debt["value"] if net_debt else None
        if ev is not None:
            add("ev", ev, "market_cap + net_debt", [shares, net_debt])
            ebitda = facts.get("ebitda")
            if ebitda and ebitda["value"]:
                add("ev_ebitda", ev / ebitda["value"], "ev / ebitda",
                    [shares, net_debt, ebitda])
    return result
