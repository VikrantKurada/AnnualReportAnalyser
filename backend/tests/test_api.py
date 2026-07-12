import json

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.providers.base import ChatResult


@pytest.fixture
def client(tmp_path, monkeypatch):
    # background ingestion must not hit the network in tests
    from app.ingest import pipeline

    def fake_ingest(conn, name, source_mode, embedder=None, embed_model=""):
        cid = pipeline.find_or_create_company(conn, name, source_mode)
        db.update(conn, "companies", cid, {"status": "ready"})
        return cid

    monkeypatch.setattr(pipeline, "ingest_company", fake_ingest)
    app = main.create_app(db_path=str(tmp_path / "api.db"))
    with TestClient(app) as c:
        yield c


def test_personas_seeded_and_crud(client):
    personas = client.get("/api/personas").json()
    names = {p["name"] for p in personas}
    assert {"CFO", "Wall Street Analyst"} <= names
    assert all(p["builtin"] == 1 for p in personas)

    created = client.post("/api/personas", json={
        "name": "Value Investor", "system_prompt": "Think like Buffett."}).json()
    assert created["id"] > 0
    updated = client.put(f"/api/personas/{created['id']}", json={
        "name": "Value Investor", "system_prompt": "Margin of safety first.",
        "web_enabled": False}).json()
    assert updated["web_enabled"] == 0
    assert client.delete(f"/api/personas/{created['id']}").json()["ok"]


def test_company_fetch_and_lifecycle(client):
    company = client.post("/api/companies/fetch", json={
        "name": "Acme", "source_mode": "edgar"}).json()
    cid = company["id"]
    assert company["status"] in ("queued", "ready")

    got = client.get(f"/api/companies/{cid}").json()
    assert got["name"] == "Acme"
    assert isinstance(got["reports"], list)

    assert client.post(f"/api/companies/{cid}/save", json={"saved": True}).json()["saved"]
    companies = client.get("/api/companies").json()
    assert any(c["id"] == cid and c["saved"] == 1 for c in companies)

    assert client.delete(f"/api/companies/{cid}").json()["ok"]
    assert client.get(f"/api/companies/{cid}").status_code == 404


def test_fetch_rejects_bad_source_mode(client):
    r = client.post("/api/companies/fetch", json={"name": "X", "source_mode": "carrier-pigeon"})
    assert r.status_code == 422


def test_settings_roundtrip_masks_keys(client):
    s = client.get("/api/settings").json()
    assert s["llm_provider"] == "ollama"
    client.put("/api/settings", json={"openai_api_key": "sk-secret", "llm_model": "m2"})
    s2 = client.get("/api/settings").json()
    assert s2["openai_api_key"] == "••••••••"
    assert s2["llm_model"] == "m2"
    # sending the mask back must not clobber the stored secret
    client.put("/api/settings", json={"openai_api_key": "••••••••"})
    conn = db.get_conn(client.app.state.db_path)
    from app import settings as settings_mod
    assert settings_mod.get_setting(conn, "openai_api_key") == "sk-secret"
    conn.close()

    r = client.put("/api/settings", json={"hacker_key": "x"})
    assert r.status_code == 422


def test_tokens_endpoint(client):
    conn = db.get_conn(client.app.state.db_path)
    from app import tokens
    tokens.record_usage(conn, "sess-a", "ollama", "glm", 100, 40, "chat")
    conn.close()
    data = client.get("/api/tokens", params={"session_key": "sess-a"}).json()
    assert data["session"]["input_tokens"] == 100
    assert data["all_time"]["output_tokens"] == 40
    assert len(data["recent"]) == 1


def test_chat_session_flow(client, monkeypatch):
    from app.api import chat_api

    def fake_turn(conn, session_id, text, session_key, web_enabled=False,
                  mcp_enabled=False, llm=None, embedder=None):
        db.insert(conn, "chat_messages", {"session_id": session_id, "role": "user",
                                          "content": text})
        db.insert(conn, "chat_messages", {"session_id": session_id,
                                          "role": "assistant", "content": "hello"})
        return {"content": "hello", "citations": [], "tool_trace": []}

    monkeypatch.setattr(chat_api.chat_mod, "run_chat_turn", fake_turn)

    company = client.post("/api/companies/fetch", json={"name": "Acme"}).json()
    session = client.post("/api/chat/sessions", json={
        "scope_type": "company", "scope_id": company["id"]}).json()
    reply = client.post(f"/api/chat/sessions/{session['id']}/messages", json={
        "text": "hi", "session_key": "s"}).json()
    assert reply["content"] == "hello"
    msgs = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_project_flow_with_metrics(client):
    conn = db.get_conn(client.app.state.db_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar",
                                        "status": "ready"})
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "revenue", "label": "Revenue",
                              "value": 100.0, "source_kind": "xbrl"})
    db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                              "metric": "net_income", "label": "Net income",
                              "value": 20.0, "source_kind": "xbrl"})
    conn.close()

    project = client.post("/api/projects", json={"name": "Compare"}).json()
    pid = project["id"]
    client.post(f"/api/projects/{pid}/companies", json={"company_id": cid})

    cmp_ = client.get(f"/api/projects/{pid}/compare").json()
    assert cmp_["companies"][0]["id"] == cid

    metrics = client.post(f"/api/projects/{pid}/metrics", json={
        "name": "NI margin", "formula": "net_income / revenue"}).json()
    assert metrics[0]["results"][str(cid)]["value"] == 0.2

    bad = client.post(f"/api/projects/{pid}/metrics", json={
        "name": "bad", "formula": "import os"})
    assert bad.status_code == 422


def test_trace_endpoint(client):
    conn = db.get_conn(client.app.state.db_path)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar"})
    fid = db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                                    "metric": "revenue", "value": 5.0,
                                    "source_kind": "xbrl",
                                    "source_ref": json.dumps({"tag": "Revenues"})})
    conn.close()
    trace = client.get(f"/api/trace/fact/{fid}").json()
    assert trace["detail"]["tag"] == "Revenues"
    assert client.get("/api/trace/fact/99999").status_code == 404
    assert client.get("/api/trace/bogus/1").status_code == 422


def test_mcp_server_crud(client):
    r = client.post("/api/mcp/servers", json={"name": "calc", "transport": "stdio"})
    assert r.status_code == 422  # stdio needs a command
    server = client.post("/api/mcp/servers", json={
        "name": "calc", "transport": "stdio", "command": "calc-server"}).json()
    assert server["enabled"] == 1
    assert client.delete(f"/api/mcp/servers/{server['id']}").json()["ok"]
