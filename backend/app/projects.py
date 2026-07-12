"""Projects: compare saved company profiles, derive custom metrics, persist results."""
import json
import re
import sqlite3

from . import db, rag
from .analysis import formula


def compare(conn: sqlite3.Connection, project_id: int) -> dict:
    companies = db.query(conn,
        "SELECT c.id, c.name, c.ticker FROM project_companies pc"
        " JOIN companies c ON c.id = pc.company_id WHERE pc.project_id = ?"
        " ORDER BY c.name", (project_id,))
    years: set[int] = set()
    rows: dict[str, dict] = {}
    for company in companies:
        pivot = rag.fact_context(conn, company["id"])
        years.update(pivot["years"])
        for m in pivot["metrics"]:
            row = rows.setdefault(m["metric"], {
                "metric": m["metric"], "label": m["label"],
                "unit": m["unit"], "values": {}, "fact_ids": {}})
            row["values"][str(company["id"])] = m["values"]
            row["fact_ids"][str(company["id"])] = m["fact_ids"]
    return {"companies": companies, "years": sorted(years, reverse=True),
            "rows": list(rows.values())}


def _latest_year_values(conn, company_id: int) -> tuple[int | None, dict, dict]:
    """Latest fiscal year with facts, its {metric: value} and {metric: fact_id}."""
    rows = db.query(conn,
        "SELECT id, metric, fiscal_year, value FROM facts"
        " WHERE company_id = ? AND value IS NOT NULL"
        " AND source_kind != 'derived' ORDER BY fiscal_year DESC", (company_id,))
    if not rows:
        return None, {}, {}
    latest = rows[0]["fiscal_year"]
    values = {r["metric"]: r["value"] for r in rows if r["fiscal_year"] == latest}
    fact_ids = {r["metric"]: r["id"] for r in rows if r["fiscal_year"] == latest}
    return latest, values, fact_ids


def add_custom_metric(conn: sqlite3.Connection, project_id: int, name: str,
                      description: str, formula_expr: str) -> int:
    """Validate the formula against every project company and store results
    with per-company input traces. Raises ValueError on a bad formula."""
    companies = db.query(conn,
        "SELECT company_id FROM project_companies WHERE project_id = ?", (project_id,))
    if not companies:
        raise ValueError("project has no companies")

    variables = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", formula_expr))
    results, trace = {}, {}
    for c in companies:
        cid = c["company_id"]
        year, values, fact_ids = _latest_year_values(conn, cid)
        if year is None:
            results[str(cid)] = {"value": None, "error": "no facts"}
            continue
        value = formula.safe_eval(formula_expr, values)  # raises on bad formula
        results[str(cid)] = {"value": value, "fiscal_year": year}
        trace[str(cid)] = {"formula": formula_expr, "fiscal_year": year,
                           "inputs": {v: {"value": values[v], "fact_id": fact_ids[v]}
                                      for v in variables if v in values}}

    return db.insert(conn, "project_metrics", {
        "project_id": project_id, "name": name, "description": description,
        "formula": formula_expr, "results_json": json.dumps(results),
        "trace_json": json.dumps(trace)})


SUGGEST_PROMPT = """You design financial comparison metrics. Given available metric \
names and the user's goal, propose ONE derived metric as JSON:
{"name": str, "description": str, "formula": str}
The formula may only use the available metric names with + - * / and parentheses."""


def suggest_metric(conn: sqlite3.Connection, project_id: int, prompt: str,
                   llm=None, session_key: str = "") -> dict:
    if llm is None:
        from .providers import registry
        llm = registry.get_llm(conn, session_key)

    available: set[str] = set()
    for c in db.query(conn, "SELECT company_id FROM project_companies"
                            " WHERE project_id = ?", (project_id,)):
        _, values, _ = _latest_year_values(conn, c["company_id"])
        available.update(values)

    result = llm.chat([
        {"role": "system", "content": SUGGEST_PROMPT},
        {"role": "user", "content": f"Available metrics: {sorted(available)}\n"
                                    f"Goal: {prompt}"},
    ], json_mode=True, context=f"suggest_metric:{project_id}")

    from .analysis.analyze import _parse_json
    suggestion = _parse_json(result.content or "")
    for key in ("name", "formula"):
        if not suggestion.get(key):
            raise ValueError(f"model suggestion missing {key!r}")
    return {"name": suggestion["name"],
            "description": suggestion.get("description", ""),
            "formula": suggestion["formula"]}


COMPARE_PROMPT = """You are a financial analyst comparing companies. Use ONLY the \
comparison table provided; cite fact ids like "fact:12" where given. Respond as JSON:
{"summary": str, "comparison": [{"statement": str, "citations": [str]}], "verdict": str}"""


def run_project_analysis(conn: sqlite3.Connection, project_id: int,
                         session_key: str, persona_id: int | None = None,
                         llm=None) -> int:
    if llm is None:
        from .providers import registry
        llm = registry.get_llm(conn, session_key)

    comparison = compare(conn, project_id)
    system = COMPARE_PROMPT
    if persona_id:
        rows = db.query(conn, "SELECT * FROM personas WHERE id=?", (persona_id,))
        if rows:
            system = f"{rows[0]['system_prompt']}\n\n{system}"

    lines = []
    for row in comparison["rows"]:
        for company in comparison["companies"]:
            cid = str(company["id"])
            values = row["values"].get(cid, {})
            ids = row["fact_ids"].get(cid, {})
            for year, value in values.items():
                if value is not None:
                    lines.append(f"[fact:{ids[year]}] {company['name']} "
                                 f"{row['label']} FY{year} = {value}")

    metrics_rows = db.query(conn, "SELECT * FROM project_metrics WHERE project_id = ?",
                            (project_id,))
    for m in metrics_rows:
        lines.append(f"Custom metric {m['name']} ({m['formula']}): {m['results_json']}")

    result = llm.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": "COMPARISON TABLE:\n" + "\n".join(lines) +
            "\n\nProduce the JSON comparison now."},
    ], json_mode=True, context=f"project_analysis:{project_id}")

    from .analysis.analyze import _parse_json
    content = _parse_json(result.content or "")
    return db.insert(conn, "analyses", {
        "project_id": project_id, "persona_id": persona_id, "kind": "comparison",
        "content_json": json.dumps(content),
        "provider": getattr(llm, "provider_name", None),
        "model": getattr(llm, "model", None)})
