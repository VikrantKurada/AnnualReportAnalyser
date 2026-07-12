"""Tool-enabled chat anchored in the stored company/project data.

Tools: document retrieval, financial facts, optional web search (cached), and
optional user-configured MCP servers. Citations in the final answer are
extracted as [chunk:N]/[fact:N] markers and stored with the message.
"""
import json
import re
import sqlite3

from . import db, mcp_client, rag, web

MAX_TOOL_ROUNDS = 6
HISTORY_LIMIT = 20

BASE_PROMPT = """You are a financial analysis assistant answering questions about \
a company using its stored annual-report data. Prefer the search_documents and \
get_financial_facts tools over guessing. When you state facts from tool results, \
cite them inline with the markers you were given, e.g. [chunk:12] or [fact:34]. \
Be concise and precise with numbers."""

CITATION_RE = re.compile(r"\[(chunk|fact):(\d+)\]")
MCP_NAME_RE = re.compile(r"^mcp_(\d+)_(.+)$")


def run_chat_turn(conn: sqlite3.Connection, session_id: int, user_text: str,
                  session_key: str, web_enabled: bool = False,
                  mcp_enabled: bool = False, llm=None, embedder=None) -> dict:
    if llm is None:
        from .providers import registry
        llm = registry.get_llm(conn, session_key)
        embedder = embedder or registry.get_embedder(conn)

    session = db.query(conn, "SELECT * FROM chat_sessions WHERE id=?", (session_id,))[0]
    persona = None
    if session["persona_id"]:
        rows = db.query(conn, "SELECT * FROM personas WHERE id=?", (session["persona_id"],))
        persona = rows[0] if rows else None
    if persona:
        web_enabled = web_enabled and bool(persona["web_enabled"])
        mcp_enabled = mcp_enabled and bool(persona["mcp_enabled"])

    company_ids = _scope_company_ids(conn, session)
    system = BASE_PROMPT + _scope_context(conn, session, company_ids)
    if persona:
        system = f"{persona['system_prompt']}\n\n{system}"

    db.insert(conn, "chat_messages", {"session_id": session_id, "role": "user",
                                      "content": user_text})

    messages = [{"role": "system", "content": system}]
    for m in _history(conn, session_id):
        messages.append({"role": m["role"], "content": m["content"]})

    tools, mcp_servers = _build_tools(conn, web_enabled, mcp_enabled)
    tool_trace: list[dict] = []
    result = None

    for _ in range(MAX_TOOL_ROUNDS):
        result = llm.chat(messages, tools=tools or None,
                          context=f"chat:{session_id}")
        if not result.tool_calls:
            break
        messages.append({"role": "assistant", "content": result.content,
                         "tool_calls": result.tool_calls})
        for tc in result.tool_calls:
            output = _run_tool(conn, tc, company_ids, embedder, mcp_servers)
            tool_trace.append({"name": tc["name"], "arguments": tc["arguments"],
                               "output": output[:2000]})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": output})

    content = result.content if result else None
    if not content or not content.strip():
        # tool loop exhausted without an answer: withhold tools to force one
        messages.append({"role": "user", "content":
                         "Answer the question now using the information gathered"
                         " above. Do not request any more tools."})
        final = llm.chat(messages, context=f"chat:{session_id}")
        content = final.content
    content = content or "(no response)"
    citations = _extract_citations(content)
    db.insert(conn, "chat_messages", {
        "session_id": session_id, "role": "assistant", "content": content,
        "citations_json": json.dumps(citations),
        "tool_calls_json": json.dumps(tool_trace)})
    return {"content": content, "citations": citations, "tool_trace": tool_trace}


def _scope_company_ids(conn, session) -> list[int]:
    if session["scope_type"] == "company" and session["scope_id"]:
        return [session["scope_id"]]
    if session["scope_type"] == "project" and session["scope_id"]:
        rows = db.query(conn, "SELECT company_id FROM project_companies WHERE project_id=?",
                        (session["scope_id"],))
        return [r["company_id"] for r in rows]
    return []


def _scope_context(conn, session, company_ids: list[int]) -> str:
    parts = []
    for cid in company_ids:
        rows = db.query(conn, "SELECT name FROM companies WHERE id=?", (cid,))
        if not rows:
            continue
        pivot = rag.fact_context(conn, cid)
        lines = [f"\n\nCOMPANY: {rows[0]['name']} — key facts:"]
        for m in pivot["metrics"][:20]:
            for year in pivot["years"][:4]:
                y = str(year)
                if y in m["values"] and m["values"][y] is not None:
                    lines.append(f"[fact:{m['fact_ids'][y]}] {m['label']} FY{y} = "
                                 f"{m['values'][y]} {m['unit'] or ''}".rstrip())
        parts.append("\n".join(lines))
    return "".join(parts)


def _history(conn, session_id) -> list[dict]:
    rows = db.query(conn,
        "SELECT role, content FROM chat_messages WHERE session_id = ?"
        " ORDER BY id DESC LIMIT ?", (session_id, HISTORY_LIMIT))
    return list(reversed(rows))


def _build_tools(conn, web_enabled: bool, mcp_enabled: bool):
    tools = [
        {"type": "function", "function": {
            "name": "search_documents",
            "description": "Semantic search over the company's annual reports. "
                           "Returns excerpts tagged [chunk:id] for citation.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "get_financial_facts",
            "description": "All stored financial facts and ratios by fiscal year, "
                           "tagged [fact:id] for citation.",
            "parameters": {"type": "object", "properties": {}}}},
    ]
    if web_enabled:
        tools.append({"type": "function", "function": {
            "name": "web_search",
            "description": "Search the web (results are cached).",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}}, "required": ["query"]}}})

    mcp_servers: dict[int, dict] = {}
    if mcp_enabled:
        for server in db.query(conn, "SELECT * FROM mcp_servers WHERE enabled = 1"):
            mcp_servers[server["id"]] = server
            try:
                remote_tools = mcp_client.list_tools_sync(server)
            except Exception:  # noqa: BLE001 - unreachable server: skip its tools
                continue
            for t in remote_tools:
                tools.append({"type": "function", "function": {
                    "name": f"mcp_{server['id']}_{t['name']}",
                    "description": f"[{server['name']}] {t['description']}"[:1024],
                    "parameters": t.get("inputSchema") or {"type": "object"}}})
    return tools, mcp_servers


def _run_tool(conn, tool_call: dict, company_ids: list[int], embedder,
              mcp_servers: dict) -> str:
    name, args = tool_call["name"], tool_call["arguments"] or {}
    try:
        if name == "search_documents":
            hits = []
            for cid in company_ids:
                hits.extend(rag.search_chunks(conn, cid, args.get("query", ""),
                                              embedder, k=6))
            hits.sort(key=lambda h: -h["score"])
            if not hits:
                return "No matching document passages found."
            return "\n\n".join(
                f"[chunk:{h['id']}] (FY{h['fiscal_year']} · {h['section']})\n{h['text'][:1200]}"
                for h in hits[:8])

        if name == "get_financial_facts":
            parts = []
            for cid in company_ids:
                pivot = rag.fact_context(conn, cid)
                for m in pivot["metrics"]:
                    for y, v in m["values"].items():
                        if v is not None:
                            parts.append(f"[fact:{m['fact_ids'][y]}] {m['label']} "
                                         f"FY{y} = {v} {m['unit'] or ''}".rstrip())
            return "\n".join(parts) or "No facts stored."

        if name == "web_search":
            results = web.web_search(conn, args.get("query", ""), max_results=6)
            return "\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}"
                               for r in results) or "No results."

        m = MCP_NAME_RE.match(name)
        if m and int(m.group(1)) in mcp_servers:
            return mcp_client.call_tool_sync(mcp_servers[int(m.group(1))],
                                             m.group(2), args)
        return f"Unknown tool: {name}"
    except Exception as e:  # noqa: BLE001 - tool errors go back to the model
        return f"Tool error: {e}"


def _extract_citations(content: str) -> list[dict]:
    seen, out = set(), []
    for kind, ref in CITATION_RE.findall(content):
        key = (kind, int(ref))
        if key not in seen:
            seen.add(key)
            out.append({"kind": kind, "id": int(ref)})
    return out
