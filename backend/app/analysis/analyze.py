"""LLM analysis pass with enforced citation traceability.

The model only sees context items tagged [chunk:id] / [fact:id]; any citation
it invents that is not in that set gets dropped before storage.
"""
import json
import re
import sqlite3

from .. import db, rag

RETRIEVAL_QUERIES = [
    "business overview products segments",
    "risk factors",
    "management discussion and analysis outlook",
    "liquidity and capital resources",
]

SYSTEM_PROMPT = """You are a rigorous financial analyst. Analyse the company using ONLY \
the provided context. Every claim must cite its sources using the exact ids given \
in the context, e.g. "chunk:12" or "fact:34". Never invent numbers or ids: all \
numeric statements must cite a fact id. Respond with JSON matching this schema:
{
  "executive_summary": str,
  "business_overview": str,
  "financial_highlights": [{"statement": str, "citations": [str]}],
  "trends": [{"metric": str, "direction": "up"|"down"|"flat", "comment": str, "citations": [str]}],
  "risks": [{"title": str, "summary": str, "citations": [str]}],
  "outlook": str
}"""

CITATION_RE = re.compile(r"^(chunk|fact):(\d+)$")


def run_analysis(conn: sqlite3.Connection, company_id: int, session_key: str,
                 persona_id: int | None = None, llm=None, embedder=None,
                 kind: str = "overview") -> int:
    if llm is None:
        from ..providers import registry
        llm = registry.get_llm(conn, session_key)
        embedder = embedder or registry.get_embedder(conn)

    company = db.query(conn, "SELECT * FROM companies WHERE id=?", (company_id,))[0]
    context, valid_ids = _build_context(conn, company_id, embedder)

    system = SYSTEM_PROMPT
    persona = None
    if persona_id:
        rows = db.query(conn, "SELECT * FROM personas WHERE id=?", (persona_id,))
        if rows:
            persona = rows[0]
            system = f"{persona['system_prompt']}\n\n{SYSTEM_PROMPT}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content":
            f"Company: {company['name']} (source: {company['source_mode']})\n\n"
            f"{context}\n\nProduce the JSON analysis now."},
    ]
    result = llm.chat(messages, json_mode=True, context=f"analysis:{company_id}")
    content = _parse_json(result.content or "")
    _validate_citations(content, valid_ids)

    return db.insert(conn, "analyses", {
        "company_id": company_id, "persona_id": persona_id, "kind": kind,
        "content_json": json.dumps(content),
        "trace_json": json.dumps(sorted(valid_ids)),
        "provider": getattr(llm, "provider_name", None),
        "model": getattr(llm, "model", None),
    })


def _build_context(conn, company_id, embedder) -> tuple[str, set[str]]:
    valid_ids: set[str] = set()
    parts: list[str] = []

    pivot = rag.fact_context(conn, company_id)
    if pivot["metrics"]:
        lines = ["FINANCIAL FACTS (metric per fiscal year):"]
        for m in pivot["metrics"]:
            for year in pivot["years"]:
                y = str(year)
                if y in m["values"] and m["values"][y] is not None:
                    fid = m["fact_ids"][y]
                    valid_ids.add(f"fact:{fid}")
                    lines.append(f"[fact:{fid}] {m['label']} FY{y} = "
                                 f"{m['values'][y]} {m['unit'] or ''}".rstrip())
        parts.append("\n".join(lines))

    seen = set()
    excerpt_lines = ["DOCUMENT EXCERPTS:"]
    for query in RETRIEVAL_QUERIES:
        for hit in rag.search_chunks(conn, company_id, query, embedder, k=4):
            if hit["id"] in seen:
                continue
            seen.add(hit["id"])
            valid_ids.add(f"chunk:{hit['id']}")
            excerpt_lines.append(
                f"[chunk:{hit['id']}] (FY{hit['fiscal_year']} · {hit['section']})\n"
                f"{hit['text'][:1500]}")
    if len(excerpt_lines) > 1:
        parts.append("\n\n".join(excerpt_lines))

    return "\n\n".join(parts), valid_ids


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"model returned no JSON object: {text[:200]}")
    return json.loads(text[start:end + 1])


def _validate_citations(content, valid_ids: set[str]) -> None:
    """Recursively drop citations that are not in the provided context."""
    if isinstance(content, dict):
        for key, value in content.items():
            if key == "citations" and isinstance(value, list):
                content[key] = [c for c in value
                                if isinstance(c, str) and c in valid_ids]
            else:
                _validate_citations(value, valid_ids)
    elif isinstance(content, list):
        for item in content:
            _validate_citations(item, valid_ids)


def get_trace(conn: sqlite3.Connection, kind: str, ref_id: int) -> dict | None:
    """Resolve a citation to full provenance for the UI."""
    if kind == "chunk":
        rows = db.query(conn,
            "SELECT c.*, r.fiscal_year, r.source_url, r.form FROM chunks c"
            " JOIN reports r ON r.id = c.report_id WHERE c.id = ?", (ref_id,))
        if not rows:
            return None
        c = rows[0]
        return {"kind": "chunk", "section": c["section"], "page": c["page"],
                "fiscal_year": c["fiscal_year"], "source_url": c["source_url"],
                "form": c["form"], "text": c["text"]}

    if kind == "fact":
        rows = db.query(conn, "SELECT * FROM facts WHERE id = ?", (ref_id,))
        if not rows:
            return None
        f = rows[0]
        detail = json.loads(f["source_ref"]) if f["source_ref"] else {}
        trace = {"kind": "fact", "metric": f["metric"], "label": f["label"],
                 "fiscal_year": f["fiscal_year"], "value": f["value"],
                 "unit": f["unit"], "source_kind": f["source_kind"],
                 "detail": detail}
        if f["source_kind"] == "derived" and detail.get("inputs"):
            trace["inputs"] = [
                {"id": i["id"], "metric": i["metric"], "label": i["label"],
                 "fiscal_year": i["fiscal_year"], "value": i["value"]}
                for input_id in detail["inputs"]
                for i in db.query(conn, "SELECT * FROM facts WHERE id = ?", (input_id,))
            ]
        if f["source_kind"] == "table" and detail.get("table_id"):
            table = db.query(conn,
                "SELECT t.caption, t.page, r.source_url FROM doc_tables t"
                " JOIN reports r ON r.id = t.report_id WHERE t.id = ?",
                (detail["table_id"],))
            if table:
                trace["table"] = table[0]
        return trace
    return None
