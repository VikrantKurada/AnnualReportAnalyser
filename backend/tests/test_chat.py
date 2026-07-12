import json

from app import chat, db, rag
from app.providers.base import ChatResult

from .test_analyze import FakeLLM
from .test_rag import FakeEmbedder


def seed(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar",
                                        "status": "ready"})
    rid = db.insert(conn, "reports", {"company_id": cid, "fiscal_year": 2025,
                                      "status": "ready"})
    chunk_id = db.insert(conn, "chunks", {"report_id": rid, "section": "Risk Factors",
                                          "seq": 0, "text": "Competition risk is high"})
    rag.embed_chunks(conn, rid, FakeEmbedder(), model_name="fake")
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "revenue", "label": "Revenue", "value": 1000.0,
                              "source_kind": "xbrl"})
    sid = db.insert(conn, "chat_sessions", {"scope_type": "company", "scope_id": cid})
    return conn, cid, chunk_id, sid


def test_chat_tool_loop_and_citations(tmp_path):
    conn, cid, chunk_id, sid = seed(tmp_path)
    llm = FakeLLM([
        ChatResult(content=None, tool_calls=[
            {"id": "c1", "name": "search_documents", "arguments": {"query": "risk"}}]),
        ChatResult(content=f"The main risk is competition [chunk:{chunk_id}]."),
    ])
    out = chat.run_chat_turn(conn, sid, "What are the risks?", "sess",
                             llm=llm, embedder=FakeEmbedder())

    assert "competition" in out["content"]
    assert out["citations"] == [{"kind": "chunk", "id": chunk_id}]

    msgs = db.query(conn, "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id", (sid,))
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert json.loads(msgs[1]["citations_json"]) == out["citations"]
    # tool call trace stored on the assistant message
    trace = json.loads(msgs[1]["tool_calls_json"])
    assert trace[0]["name"] == "search_documents"

    # second LLM call saw the tool result with the chunk marker
    second_call_msgs = llm.calls[1]["messages"]
    tool_msgs = [m for m in second_call_msgs if m["role"] == "tool"]
    assert any(f"[chunk:{chunk_id}]" in m["content"] for m in tool_msgs)


def test_chat_web_tool_only_when_enabled(tmp_path, monkeypatch):
    conn, cid, chunk_id, sid = seed(tmp_path)

    llm = FakeLLM([ChatResult(content="no tools needed")])
    chat.run_chat_turn(conn, sid, "hi", "sess", llm=llm, embedder=FakeEmbedder(),
                       web_enabled=False)
    names = [t["function"]["name"] for t in llm.calls[0]["tools"]]
    assert "web_search" not in names
    assert "search_documents" in names
    assert "get_financial_facts" in names

    llm2 = FakeLLM([ChatResult(content="ok")])
    chat.run_chat_turn(conn, sid, "hi", "sess", llm=llm2, embedder=FakeEmbedder(),
                       web_enabled=True)
    names2 = [t["function"]["name"] for t in llm2.calls[0]["tools"]]
    assert "web_search" in names2


def test_chat_persona_prompt_and_gating(tmp_path):
    conn, cid, chunk_id, sid = seed(tmp_path)
    pid = db.insert(conn, "personas", {"name": "CFO", "system_prompt": "You are the CFO.",
                                       "web_enabled": 0})
    db.update(conn, "chat_sessions", sid, {"persona_id": pid})

    llm = FakeLLM([ChatResult(content="ok")])
    chat.run_chat_turn(conn, sid, "hi", "sess", llm=llm, embedder=FakeEmbedder(),
                       web_enabled=True)
    assert "You are the CFO." in llm.calls[0]["messages"][0]["content"]
    # persona forbids web even though the request enabled it
    names = [t["function"]["name"] for t in llm.calls[0]["tools"]]
    assert "web_search" not in names


def test_chat_mcp_tools_dispatch(tmp_path, monkeypatch):
    conn, cid, chunk_id, sid = seed(tmp_path)
    server_id = db.insert(conn, "mcp_servers", {"name": "calc", "transport": "stdio",
                                                "command": "calc-server"})

    monkeypatch.setattr(chat.mcp_client, "list_tools_sync", lambda server: [
        {"name": "add", "description": "Add numbers",
         "inputSchema": {"type": "object", "properties": {}}}])
    called = {}

    def fake_call(server, name, args):
        called["server"] = server["name"]
        called["name"] = name
        called["args"] = args
        return "42"

    monkeypatch.setattr(chat.mcp_client, "call_tool_sync", fake_call)

    llm = FakeLLM([
        ChatResult(content=None, tool_calls=[
            {"id": "c1", "name": f"mcp_{server_id}_add", "arguments": {"a": 40, "b": 2}}]),
        ChatResult(content="The answer is 42."),
    ])
    out = chat.run_chat_turn(conn, sid, "add 40+2", "sess", llm=llm,
                             embedder=FakeEmbedder(), mcp_enabled=True)
    assert called == {"server": "calc", "name": "add", "args": {"a": 40, "b": 2}}
    assert out["content"] == "The answer is 42."

    names = [t["function"]["name"] for t in llm.calls[0]["tools"]]
    assert f"mcp_{server_id}_add" in names


def test_chat_history_included(tmp_path):
    conn, cid, chunk_id, sid = seed(tmp_path)
    llm = FakeLLM([ChatResult(content="first answer")])
    chat.run_chat_turn(conn, sid, "first question", "sess", llm=llm,
                       embedder=FakeEmbedder())
    llm2 = FakeLLM([ChatResult(content="second answer")])
    chat.run_chat_turn(conn, sid, "second question", "sess", llm=llm2,
                       embedder=FakeEmbedder())
    contents = [m.get("content") or "" for m in llm2.calls[0]["messages"]]
    assert any("first question" in c for c in contents)
    assert any("first answer" in c for c in contents)
