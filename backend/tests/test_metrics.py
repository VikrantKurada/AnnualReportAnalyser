import pytest

from app.analysis import formula, metrics


def fact(fid, metric, fy, value):
    return {"id": fid, "metric": metric, "fiscal_year": fy, "value": value}


FACTS = [
    fact(1, "revenue", 2025, 1000.0), fact(2, "revenue", 2024, 800.0),
    fact(3, "net_income", 2025, 200.0), fact(4, "net_income", 2024, 160.0),
    fact(5, "operating_income", 2025, 300.0),
    fact(6, "equity", 2025, 500.0),
    fact(7, "current_assets", 2025, 400.0), fact(8, "current_liabilities", 2025, 200.0),
    fact(9, "total_liabilities", 2025, 900.0),
]


def by_key(rows):
    return {(r["metric"], r["fiscal_year"]): r for r in rows}


def test_compute_ratios_values_and_trace():
    out = by_key(metrics.compute_ratios(FACTS))
    nm = out[("net_margin", 2025)]
    assert nm["value"] == pytest.approx(0.2)
    assert "net_income / revenue" in nm["formula"]
    assert set(nm["inputs"]) == {3, 1}

    assert out[("operating_margin", 2025)]["value"] == pytest.approx(0.3)
    assert out[("roe", 2025)]["value"] == pytest.approx(0.4)
    assert out[("current_ratio", 2025)]["value"] == pytest.approx(2.0)
    assert out[("debt_to_equity", 2025)]["value"] == pytest.approx(1.8)
    assert out[("revenue_growth_yoy", 2025)]["value"] == pytest.approx(0.25)
    assert out[("net_income_growth_yoy", 2025)]["value"] == pytest.approx(0.25)
    # 2024 has no equity/current data -> those ratios absent
    assert ("roe", 2024) not in out
    assert ("revenue_growth_yoy", 2024) not in out  # no 2023 revenue


def test_compute_ratios_zero_division_skipped():
    rows = [fact(1, "revenue", 2025, 0.0), fact(2, "net_income", 2025, 5.0)]
    assert by_key(metrics.compute_ratios(rows)) == {}


ANALYST_FACTS = [
    fact(1, "revenue", 2025, 1000.0), fact(2, "revenue", 2024, 800.0),
    fact(3, "net_income", 2025, 200.0), fact(4, "net_income", 2024, 160.0),
    fact(5, "operating_income", 2025, 300.0), fact(6, "equity", 2025, 500.0),
    fact(7, "current_assets", 2025, 400.0), fact(8, "current_liabilities", 2025, 200.0),
    fact(9, "total_liabilities", 2025, 900.0),
    fact(10, "gross_profit", 2025, 450.0),
    fact(11, "depreciation_amortization", 2025, 50.0),
    fact(12, "operating_cash_flow", 2025, 280.0),
    fact(13, "capex", 2025, 80.0),
    fact(14, "long_term_debt", 2025, 600.0), fact(15, "short_term_debt", 2025, 100.0),
    fact(16, "cash", 2025, 150.0),
    fact(17, "total_assets", 2025, 1400.0),
    fact(18, "income_tax", 2025, 60.0), fact(19, "pretax_income", 2025, 260.0),
    fact(20, "inventory", 2025, 90.0), fact(21, "receivables", 2025, 120.0),
    fact(22, "payables", 2025, 110.0),
    fact(23, "cost_of_revenue", 2025, 550.0),
    fact(24, "rnd_expense", 2025, 70.0),
    fact(25, "interest_expense", 2025, 30.0),
    fact(26, "shares_diluted_wa", 2025, 100.0),
    fact(27, "dividends_paid", 2025, 40.0), fact(28, "buybacks", 2025, 60.0),
    fact(29, "revenue", 2023, 700.0), fact(30, "revenue", 2022, 500.0),
]


def test_compute_derived_values():
    out = by_key(metrics.compute_derived_values(ANALYST_FACTS))
    ebitda = out[("ebitda", 2025)]
    assert ebitda["value"] == pytest.approx(350.0)
    assert ebitda["unit"] == "USD"
    assert set(ebitda["inputs"]) == {5, 11}

    assert out[("fcf", 2025)]["value"] == pytest.approx(200.0)  # 280 - 80
    assert out[("total_debt", 2025)]["value"] == pytest.approx(700.0)
    assert out[("net_debt", 2025)]["value"] == pytest.approx(550.0)
    # chained metric cites base fact ids only
    assert set(out[("net_debt", 2025)]["inputs"]) == {14, 15, 16}
    assert out[("invested_capital", 2025)]["value"] == pytest.approx(1200.0)
    # 2024 lacks components -> skipped
    assert ("ebitda", 2024) not in out


def test_derived_values_partial_debt():
    rows = [fact(1, "long_term_debt", 2025, 500.0)]
    out = by_key(metrics.compute_derived_values(rows))
    assert out[("total_debt", 2025)]["value"] == 500.0  # short-term optional
    assert ("net_debt", 2025) not in out  # cash missing


def all_facts():
    derived = metrics.compute_derived_values(ANALYST_FACTS)
    with_ids = list(ANALYST_FACTS)
    next_id = 100
    for d in derived:
        with_ids.append(fact(next_id, d["metric"], d["fiscal_year"], d["value"]))
        next_id += 1
    return with_ids


def test_analyst_ratios_margins_and_returns():
    out = by_key(metrics.compute_ratios(all_facts()))
    assert out[("gross_margin", 2025)]["value"] == pytest.approx(0.45)
    assert out[("ebitda_margin", 2025)]["value"] == pytest.approx(0.35)
    assert out[("fcf_margin", 2025)]["value"] == pytest.approx(0.2)
    assert out[("roa", 2025)]["value"] == pytest.approx(200.0 / 1400.0)
    # roic: tax rate 60/260 ≈ 0.2308 -> nopat 300*0.7692 ≈ 230.77 / 1200
    assert out[("roic", 2025)]["value"] == pytest.approx(230.77 / 1200, rel=1e-3)
    assert out[("effective_tax_rate", 2025)]["value"] == pytest.approx(60 / 260)
    assert out[("net_margin", 2025)]["unit"] == "ratio"


def test_roic_tax_rate_clamped():
    rows = all_facts()
    # absurd tax entry: rate would be 90%, must clamp to 50%
    rows = [r for r in rows if r["metric"] != "income_tax"]
    rows.append(fact(18, "income_tax", 2025, 234.0))
    out = by_key(metrics.compute_ratios(rows))
    assert out[("roic", 2025)]["value"] == pytest.approx(300 * 0.5 / 1200, rel=1e-3)


def test_analyst_ratios_efficiency_and_days():
    out = by_key(metrics.compute_ratios(all_facts()))
    assert out[("asset_turnover", 2025)]["value"] == pytest.approx(1000 / 1400)
    assert out[("asset_turnover", 2025)]["unit"] == "x"
    assert out[("inventory_turnover", 2025)]["value"] == pytest.approx(550 / 90)
    assert out[("dso", 2025)]["value"] == pytest.approx(120 / 1000 * 365)
    assert out[("dso", 2025)]["unit"] == "days"
    assert out[("dio", 2025)]["value"] == pytest.approx(90 / 550 * 365)
    assert out[("dpo", 2025)]["value"] == pytest.approx(110 / 550 * 365)
    ccc = out[("ccc", 2025)]
    assert ccc["value"] == pytest.approx(
        120 / 1000 * 365 + 90 / 550 * 365 - 110 / 550 * 365)
    assert set(ccc["inputs"]) >= {21, 20, 22}
    assert out[("quick_ratio", 2025)]["value"] == pytest.approx((400 - 90) / 200)
    assert out[("interest_coverage", 2025)]["value"] == pytest.approx(10.0)
    assert out[("net_debt_to_ebitda", 2025)]["value"] == pytest.approx(550 / 350)
    assert out[("equity_multiplier", 2025)]["value"] == pytest.approx(2.8)
    assert out[("ocf_to_net_income", 2025)]["value"] == pytest.approx(1.4)
    assert out[("rnd_intensity", 2025)]["value"] == pytest.approx(0.07)
    assert out[("capex_intensity", 2025)]["value"] == pytest.approx(0.08)


def test_analyst_ratios_per_share_and_payout():
    out = by_key(metrics.compute_ratios(all_facts()))
    assert out[("fcf_per_share", 2025)]["value"] == pytest.approx(2.0)
    assert out[("fcf_per_share", 2025)]["unit"] == "USD/share"
    assert out[("dividends_per_share", 2025)]["value"] == pytest.approx(0.4)
    assert out[("book_value_per_share", 2025)]["value"] == pytest.approx(5.0)
    assert out[("revenue_per_share", 2025)]["value"] == pytest.approx(10.0)
    assert out[("dividend_payout", 2025)]["value"] == pytest.approx(0.2)
    assert out[("shareholder_payout", 2025)]["value"] == pytest.approx(0.5)  # (40+60)/200


def test_growth_and_cagr():
    out = by_key(metrics.compute_ratios(all_facts()))
    assert out[("revenue_growth_yoy", 2025)]["value"] == pytest.approx(0.25)
    # CAGR 3y: (1000/500)^(1/3) - 1
    assert out[("revenue_cagr_3y", 2025)]["value"] == pytest.approx(2 ** (1 / 3) - 1)
    assert set(out[("revenue_cagr_3y", 2025)]["inputs"]) == {1, 30}
    assert ("net_income_cagr_3y", 2025) not in out  # no 2022 net income


def test_safe_eval_basic():
    assert formula.safe_eval("a / b", {"a": 10, "b": 4}) == 2.5
    assert formula.safe_eval("(a + b) * 2 - 1", {"a": 1, "b": 2}) == 5
    assert formula.safe_eval("-a", {"a": 3}) == -3


def test_safe_eval_rejects_malicious():
    for expr in ("__import__('os')", "a.__class__", "exec('x=1')", "a if b else c",
                 "[1,2][0]", "lambda: 1"):
        with pytest.raises(ValueError):
            formula.safe_eval(expr, {"a": 1, "b": 2, "c": 3})


def test_safe_eval_unknown_variable():
    with pytest.raises(ValueError, match="unknown variable"):
        formula.safe_eval("a + missing", {"a": 1})


def test_safe_eval_division_by_zero():
    with pytest.raises(ValueError, match="division by zero"):
        formula.safe_eval("a / b", {"a": 1, "b": 0})
