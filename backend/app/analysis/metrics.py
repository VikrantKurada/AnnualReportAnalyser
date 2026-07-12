"""Derived financial ratios, computed in Python with full input traceability.

Each result carries the formula and the fact ids used, so the UI can show
exactly where a number came from. The LLM never computes these.
"""

# (metric, human formula, numerator metric, denominator metric)
_RATIOS = [
    ("net_margin", "net_income / revenue", "net_income", "revenue"),
    ("operating_margin", "operating_income / revenue", "operating_income", "revenue"),
    ("roe", "net_income / equity", "net_income", "equity"),
    ("current_ratio", "current_assets / current_liabilities",
     "current_assets", "current_liabilities"),
    ("debt_to_equity", "total_liabilities / equity", "total_liabilities", "equity"),
]

_GROWTH = [
    ("revenue_growth_yoy", "revenue"),
    ("net_income_growth_yoy", "net_income"),
]

RATIO_LABELS = {
    "net_margin": "Net margin", "operating_margin": "Operating margin",
    "roe": "Return on equity", "current_ratio": "Current ratio",
    "debt_to_equity": "Debt to equity", "revenue_growth_yoy": "Revenue growth YoY",
    "net_income_growth_yoy": "Net income growth YoY",
}


def compute_ratios(facts: list[dict]) -> list[dict]:
    """facts: rows with id, metric, fiscal_year, value. Returns derived rows
    with {metric, fiscal_year, value, formula, inputs:[fact ids]}."""
    index = {(f["metric"], f["fiscal_year"]): f for f in facts
             if f.get("value") is not None}
    years = sorted({f["fiscal_year"] for f in facts}, reverse=True)
    out = []

    for year in years:
        for metric, human, num, den in _RATIOS:
            fn, fd = index.get((num, year)), index.get((den, year))
            if fn is None or fd is None or not fd["value"]:
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": fn["value"] / fd["value"], "formula": human,
                        "inputs": [fn["id"], fd["id"]]})
        for metric, base in _GROWTH:
            cur, prev = index.get((base, year)), index.get((base, year - 1))
            if cur is None or prev is None or not prev["value"]:
                continue
            out.append({"metric": metric, "fiscal_year": year,
                        "value": cur["value"] / prev["value"] - 1.0,
                        "formula": f"{base}[y] / {base}[y-1] - 1",
                        "inputs": [cur["id"], prev["id"]]})
    return out
