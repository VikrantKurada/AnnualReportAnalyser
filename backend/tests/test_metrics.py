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
