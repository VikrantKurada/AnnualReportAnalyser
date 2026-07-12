"""Personas, settings, tokens, and MCP-server management endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_mod
from .. import mcp_client
from .. import settings as settings_mod
from .. import tokens
from ..providers import registry
from .deps import get_db

router = APIRouter()


# ---------- personas ----------

class PersonaRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    enabled: bool = True
    web_enabled: bool = True
    mcp_enabled: bool = True


@router.get("/personas")
def list_personas(conn: sqlite3.Connection = Depends(get_db)):
    return db_mod.query(conn, "SELECT * FROM personas ORDER BY id")


@router.post("/personas")
def create_persona(req: PersonaRequest, conn: sqlite3.Connection = Depends(get_db)):
    pid = db_mod.insert(conn, "personas", {
        "name": req.name, "description": req.description,
        "system_prompt": req.system_prompt, "enabled": int(req.enabled),
        "web_enabled": int(req.web_enabled), "mcp_enabled": int(req.mcp_enabled)})
    return db_mod.query(conn, "SELECT * FROM personas WHERE id=?", (pid,))[0]


@router.put("/personas/{persona_id}")
def update_persona(persona_id: int, req: PersonaRequest,
                   conn: sqlite3.Connection = Depends(get_db)):
    if not db_mod.query(conn, "SELECT id FROM personas WHERE id=?", (persona_id,)):
        raise HTTPException(404, "persona not found")
    db_mod.update(conn, "personas", persona_id, {
        "name": req.name, "description": req.description,
        "system_prompt": req.system_prompt, "enabled": int(req.enabled),
        "web_enabled": int(req.web_enabled), "mcp_enabled": int(req.mcp_enabled)})
    return db_mod.query(conn, "SELECT * FROM personas WHERE id=?", (persona_id,))[0]


@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM personas WHERE id=?", (persona_id,))
    conn.commit()
    return {"ok": True}


# ---------- settings ----------

@router.get("/settings")
def get_settings(conn: sqlite3.Connection = Depends(get_db)):
    return settings_mod.masked_settings(conn)


@router.put("/settings")
def put_settings(values: dict, conn: sqlite3.Connection = Depends(get_db)):
    known = set(settings_mod.DEFAULTS)
    unknown = set(values) - known
    if unknown:
        raise HTTPException(422, f"unknown settings: {sorted(unknown)}")
    settings_mod.update_settings(conn, values)
    return settings_mod.masked_settings(conn)


@router.get("/settings/providers/test")
def test_provider(conn: sqlite3.Connection = Depends(get_db)):
    try:
        llm = registry.get_llm(conn, session_key="provider-test")
        result = llm.chat([{"role": "user", "content":
                            "Reply with the single word: OK"}], context="provider-test")
        return {"ok": True, "provider": llm.provider_name, "model": llm.model,
                "reply": (result.content or "")[:100]}
    except Exception as e:  # noqa: BLE001 - report, don't 500
        return {"ok": False, "error": str(e)}


# ---------- tokens ----------

@router.get("/tokens")
def get_tokens(session_key: str = "", conn: sqlite3.Connection = Depends(get_db)):
    return {
        "session": tokens.session_totals(conn, session_key),
        "all_time": tokens.totals_all(conn),
        "recent": tokens.session_calls(conn, session_key, limit=30),
    }


# ---------- MCP servers ----------

class McpServerRequest(BaseModel):
    name: str
    transport: str = "stdio"  # "stdio" | "http"
    command: str | None = None
    url: str | None = None
    args_json: str = "[]"
    enabled: bool = True


@router.get("/mcp/servers")
def list_mcp_servers(conn: sqlite3.Connection = Depends(get_db)):
    return db_mod.query(conn, "SELECT * FROM mcp_servers ORDER BY id")


@router.post("/mcp/servers")
def create_mcp_server(req: McpServerRequest,
                      conn: sqlite3.Connection = Depends(get_db)):
    if req.transport == "stdio" and not req.command:
        raise HTTPException(422, "stdio transport requires a command")
    if req.transport == "http" and not req.url:
        raise HTTPException(422, "http transport requires a url")
    sid = db_mod.insert(conn, "mcp_servers", {
        "name": req.name, "transport": req.transport, "command": req.command,
        "url": req.url, "args_json": req.args_json, "enabled": int(req.enabled)})
    return db_mod.query(conn, "SELECT * FROM mcp_servers WHERE id=?", (sid,))[0]


@router.delete("/mcp/servers/{server_id}")
def delete_mcp_server(server_id: int, conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
    conn.commit()
    return {"ok": True}


@router.put("/mcp/servers/{server_id}/enabled")
def toggle_mcp_server(server_id: int, enabled: bool,
                      conn: sqlite3.Connection = Depends(get_db)):
    db_mod.update(conn, "mcp_servers", server_id, {"enabled": int(enabled)})
    return {"ok": True}


@router.get("/mcp/servers/{server_id}/tools")
def mcp_server_tools(server_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = db_mod.query(conn, "SELECT * FROM mcp_servers WHERE id=?", (server_id,))
    if not rows:
        raise HTTPException(404, "server not found")
    try:
        return {"ok": True, "tools": mcp_client.list_tools_sync(rows[0])}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "tools": []}
