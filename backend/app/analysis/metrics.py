"""Derived financial metrics, computed in Python with full input traceability.

Two passes: `compute_derived_values` builds currency-valued composites (EBITDA,
FCF, debt aggregates) that get stored as facts; `compute_ratios` then derives
ratios over base + composite facts. Every result carries the formula and the
fact ids used so the UI can show exactly where a number came from. The LLM
never computes these.
"""

# ---- pass 1: derived currency values (chains flatten to base fact ids) ----

# ---- pass 2 tables: (metric, numerator, denominator, unit) ----
_SIMPLE_RATIOS = [
    ("gross_margin", "gross_profit", "revenue", "ratio"),
    ("operating_margin", "operating_income", "revenue", "ratio"),
    ("ebitda_margin", "ebitda", "revenue", "ratio"),
    ("net_margin", "net_income", "revenue", "ratio"),
    ("fcf_margin", "fcf", "revenue", "ratio"),
    ("rnd_intensity", "rnd_expense", "revenue", "ratio"),
    ("sga_ratio", "sga_expense", "revenue", "ratio"),
    ("capex_intensity", "capex", "revenue", "ratio"),
    ("effective_tax_rate", "income_tax", "pretax_income", "ratio"),
    ("roe", "net_income", "equity", "ratio"),
    ("roa", "net_income", "total_assets", "ratio"),
    ("dividend_payout", "dividends_paid", "net_income", "ratio"),
    ("current_ratio", "current_assets", "current_liabilities", "x"),
    ("cash_ratio", "cash", "current_liabilities", "x"),
    ("debt_to_equity", "total_liabilities", "equity", "x"),
    ("net_debt_to_ebitda", "net_debt", "ebitda", "x"),
    ("interest_coverage", "operating_income", "interest_expense", "x"),
    ("asset_turnover", "revenue", "total_assets", "x"),
    ("inventory_turnover", "cost_of_revenue", "inventory", "x"),
    ("receivables_turnover", "revenue", "receivables", "x"),
    ("equity_multiplier", "total_assets", "equity", "x"),
    ("ocf_to_net_income", "operating_cash_flow", "net_income", "x"),
]

_DAYS = [  # value = num / den * 365
    ("dso", "receivables", "revenue"),
    ("dio", "inventory", "cost_of_revenue"),
    ("dpo", "payables", "cost_of_revenue"),
]

_PER_SHARE = [  # denominator: shares_diluted_wa, fallback shares_outstanding
    ("fcf_per_share", "fcf"),
    ("dividends_per_share", "dividends_paid"),
    ("book_value_per_share", "equity"),
    ("revenue_per_share", "revenue"),
]

_GROWTH = [  # (metric name, base metric)
    ("revenue_growth_yoy", "revenue"),
    ("net_income_growth_yoy", "net_income"),
    ("operating_income_growth_yoy", "operating_income"),
    ("eps_growth_yoy", "eps_diluted"),
    ("fcf_growth_yoy", "fcf"),
    ("operating_cash_flow_growth_yoy", "operating_cash_flow"),
    ("total_assets_growth_yoy", "total_assets"),
]

_CAGR = [
    ("revenue_cagr_3y", "revenue"),
    ("net_income_cagr_3y", "net_income"),
]

RATIO_LABELS = {
    # pass-1 values
    "ebitda": "EBITDA", "fcf": "Free cash flow", "total_debt": "Total debt",
    "net_debt": "Net debt", "invested_capital": "Invested capital",
    # margins & intensity
    "gross_margin": "Gross margin", "operating_margin": "Operating margin",
    "ebitda_margin": "EBITDA margin", "net_margin": "Net margin",
    "fcf_margin": "FCF margin", "rnd_intensity": "R&D intensity",
    "sga_ratio": "SG&A ratio", "capex_intensity": "Capex intensity",
    "effective_tax_rate": "Effective tax rate",
    # returns
    "roe": "Return on equity", "roa": "Return on assets",
    "roic": "Return on invested capital",
    # liquidity / leverage / efficiency
    "current_ratio": "Current ratio", "quick_ratio": "Quick ratio",
    "cash_ratio": "Cash ratio", "debt_to_equity": "Debt to equity",
    "net_debt_to_ebitda": "Net debt / EBITDA",
    "interest_coverage": "Interest coverage",
    "asset_turnover": "Asset turnover", "inventory_turnover": "Inventory turnover",
    "receivables_turnover": "Receivables turnover",
    "equity_multiplier": "Equity multiplier (leverage)",
    "ocf_to_net_income": "OCF / net income (earnings quality)",
    # working capital days
    "dso": "Days sales outstanding", "dio": "Days inventory outstanding",
    "dpo": "Days payables outstanding", "ccc": "Cash conversion cycle",
    # per share & payout
    "fcf_per_share": "FCF per share", "dividends_per_share": "Dividends per share",
    "book_value_per_share": "Book value per share",
    "revenue_per_share": "Revenue per share",
    "dividend_payout": "Dividend payout ratio",
    "shareholder_payout": "Shareholder payout (of FCF)",
    # growth
    "revenue_growth_yoy": "Revenue growth YoY",
    "net_income_growth_yoy": "Net income growth YoY",
    "operating_income_growth_yoy": "Operating income growth YoY",
    "eps_growth_yoy": "EPS growth YoY", "fcf_growth_yoy": "FCF growth YoY",
    "operating_cash_flow_growth_yoy": "Operating cash flow growth YoY",
    "total_assets_growth_yoy": "Total assets growth YoY",
    "revenue_cagr_3y": "Revenue CAGR (3y)",
    "net_income_cagr_3y": "Net income CAGR (3y)",
}


def _index(facts):
    return {(f["metric"], f["fiscal_year"]): f for f in facts
            if f.get("value") is not None}


def _years(facts):
    return sorted({f["fiscal_year"] for f in facts}, reverse=True)


def compute_derived_values(facts: list[dict]) -> list[dict]:
    """Currency composites (unit USD). Chained metrics cite base fact ids."""
    index = _index(facts)
    out = []

    for year in _years(facts):
        def get(metric):
            f = index.get((metric, year))
            return (f["value"], {f["id"]}) if f else (None, set())

        oi, oi_ids = get("operating_income")
        da, da_ids = get("depreciation_amortization")
        if oi is not None and da is not None:
            out.append(_value_row("ebitda", year,
                "operating_income + depreciation_amortization",
                oi + da, oi_ids | da_ids))

        ocf, ocf_ids = get("operating_cash_flow")
        capex, capex_ids = get("capex")
        if ocf is not None and capex is not None:
            out.append(_value_row("fcf", year, "operating_cash_flow - capex",
                                  ocf - capex, ocf_ids | capex_ids))

        ltd, ltd_ids = get("long_term_debt")
        std, std_ids = get("short_term_debt")
        debt_terms = [(v, ids, name) for v, ids, name in
                      [(ltd, ltd_ids, "long_term_debt"),
                       (std, std_ids, "short_term_debt")] if v is not None]
        total_debt = debt_ids = None
        if debt_terms:
            total_debt = sum(v for v, _, _ in debt_terms)
            debt_ids = set().union(*(ids for _, ids, _ in debt_terms))
            formula = " + ".join(name for _, _, name in debt_terms)
            out.append(_value_row("total_debt", year, formula, total_debt, debt_ids))

        cash, cash_ids = get("cash")
        if total_debt is not None and cash is not None:
            out.append(_value_row("net_debt", year, "total_debt - cash",
                                  total_debt - cash, debt_ids | cash_ids))

        equity, equity_ids = get("equity")
        if total_debt is not None and equity is not None:
            out.append(_value_row("invested_capital", year, "equity + total_debt",
                                  equity + total_debt, debt_ids | equity_ids))
    return out


def _value_row(metric, year, formula, value, inputs):
    return {"metric": metric, "fiscal_year": year, "value": value,
            "formula": formula, "inputs": sorted(inputs), "unit": "USD"}


def compute_ratios(facts: list[dict]) -> list[dict]:
    """Ratios over base + pass-1 facts. Rows: {metric, fiscal_year, value,
    formula, inputs:[fact ids], unit}."""
    index = _index(facts)
    out = []

    for year in _years(facts):
        def get(metric):
            return index.get((metric, year))

        for metric, num, den, unit in _SIMPLE_RATIOS:
            fn, fd = get(num), get(den)
            if fn is None or fd is None or not fd["value"]:
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": fn["value"] / fd["value"],
                        "formula": f"{num} / {den}",
                        "inputs": [fn["id"], fd["id"]], "unit": unit})

        for metric, num, den in _DAYS:
            fn, fd = get(num), get(den)
            if fn is None or fd is None or not fd["value"]:
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": fn["value"] / fd["value"] * 365,
                        "formula": f"{num} / {den} * 365",
                        "inputs": [fn["id"], fd["id"]], "unit": "days"})

        day_rows = {r["metric"]: r for r in out
                    if r["fiscal_year"] == year and r["metric"] in ("dso", "dio", "dpo")}
        if len(day_rows) == 3:
            out.append({"metric": "ccc", "fiscal_year": year,
                        "value": day_rows["dso"]["value"] + day_rows["dio"]["value"]
                        - day_rows["dpo"]["value"],
                        "formula": "dso + dio - dpo",
                        "inputs": sorted({i for r in day_rows.values()
                                          for i in r["inputs"]}),
                        "unit": "days"})

        ca, inv, cl = get("current_assets"), get("inventory"), get("current_liabilities")
        if ca and inv and cl and cl["value"]:
            out.append({"metric": "quick_ratio", "fiscal_year": year,
                        "value": (ca["value"] - inv["value"]) / cl["value"],
                        "formula": "(current_assets - inventory) / current_liabilities",
                        "inputs": [ca["id"], inv["id"], cl["id"]], "unit": "x"})

        oi, tax, pretax, ic = (get("operating_income"), get("income_tax"),
                               get("pretax_income"), get("invested_capital"))
        if oi and tax and pretax and ic and pretax["value"] and ic["value"]:
            rate = min(max(tax["value"] / pretax["value"], 0.0), 0.5)
            out.append({"metric": "roic", "fiscal_year": year,
                        "value": oi["value"] * (1 - rate) / ic["value"],
                        "formula": "operating_income * (1 - effective_tax_rate)"
                                   " / invested_capital",
                        "inputs": [oi["id"], tax["id"], pretax["id"], ic["id"]],
                        "unit": "ratio"})

        div, bb, fcf = get("dividends_paid"), get("buybacks"), get("fcf")
        payout_terms = [f for f in (div, bb) if f is not None]
        if payout_terms and fcf and fcf["value"]:
            out.append({"metric": "shareholder_payout", "fiscal_year": year,
                        "value": sum(f["value"] for f in payout_terms) / fcf["value"],
                        "formula": "(dividends_paid + buybacks) / fcf",
                        "inputs": [f["id"] for f in payout_terms] + [fcf["id"]],
                        "unit": "ratio"})

        shares = get("shares_diluted_wa") or get("shares_outstanding")
        if shares and shares["value"]:
            for metric, num in _PER_SHARE:
                fn = get(num)
                if fn is None:
                    continue
                out.append({"metric": metric, "fiscal_year": year,
                            "value": fn["value"] / shares["value"],
                            "formula": f"{num} / {shares['metric']}",
                            "inputs": [fn["id"], shares["id"]],
                            "unit": "USD/share"})

        for metric, base in _GROWTH:
            cur, prev = index.get((base, year)), index.get((base, year - 1))
            if cur is None or prev is None or not prev["value"] or prev["value"] < 0:
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": cur["value"] / prev["value"] - 1.0,
                        "formula": f"{base}[y] / {base}[y-1] - 1",
                        "inputs": [cur["id"], prev["id"]], "unit": "ratio"})

        for metric, base in _CAGR:
            cur, past = index.get((base, year)), index.get((base, year - 3))
            if (cur is None or past is None or cur["value"] is None
                    or not past["value"] or past["value"] < 0 or cur["value"] <= 0):
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": (cur["value"] / past["value"]) ** (1 / 3) - 1.0,
                        "formula": f"({base}[y] / {base}[y-3]) ^ (1/3) - 1",
                        "inputs": [cur["id"], past["id"]], "unit": "ratio"})
    return out
