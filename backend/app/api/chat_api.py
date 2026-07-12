import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import chat as chat_mod
from .. import db as db_mod
from .. import tokens
from .deps import get_db

router = APIRouter()


class SessionRequest(BaseModel):
    scope_type: str  # "company" | "project"
    scope_id: int
    persona_id: int | None = None
    title: str | None = None


class MessageRequest(BaseModel):
    text: str
    session_key: str = ""
    web_enabled: bool = False
    mcp_enabled: bool = False


@router.post("/chat/sessions")
def create_session(req: SessionRequest, conn: sqlite3.Connection = Depends(get_db)):
    if req.scope_type not in ("company", "project"):
        raise HTTPException(422, "scope_type must be 'company' or 'project'")
    sid = db_mod.insert(conn, "chat_sessions", {
        "scope_type": req.scope_type, "scope_id": req.scope_id,
        "persona_id": req.persona_id, "title": req.title})
    return db_mod.query(conn, "SELECT * FROM chat_sessions WHERE id=?", (sid,))[0]


@router.get("/chat/sessions")
def list_sessions(scope_type: str, scope_id: int,
                  conn: sqlite3.Connection = Depends(get_db)):
    return db_mod.query(conn,
        "SELECT * FROM chat_sessions WHERE scope_type=? AND scope_id=?"
        " ORDER BY id DESC", (scope_type, scope_id))


@router.put("/chat/sessions/{session_id}/persona")
def set_persona(session_id: int, persona_id: int | None = None,
                conn: sqlite3.Connection = Depends(get_db)):
    db_mod.update(conn, "chat_sessions", session_id, {"persona_id": persona_id})
    return {"ok": True}


@router.get("/chat/sessions/{session_id}/messages")
def list_messages(session_id: int, conn: sqlite3.Connection = Depends(get_db)):
    rows = db_mod.query(conn,
        "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,))
    for r in rows:
        r["citations"] = json.loads(r.pop("citations_json") or "[]")
        r["tool_calls"] = json.loads(r.pop("tool_calls_json") or "[]")
    return rows


@router.post("/chat/sessions/{session_id}/messages")
def send_message(session_id: int, req: MessageRequest,
                 conn: sqlite3.Connection = Depends(get_db)):
    rows = db_mod.query(conn, "SELECT id FROM chat_sessions WHERE id=?", (session_id,))
    if not rows:
        raise HTTPException(404, "session not found")
    result = chat_mod.run_chat_turn(conn, session_id, req.text, req.session_key,
                                    web_enabled=req.web_enabled,
                                    mcp_enabled=req.mcp_enabled)
    result["tokens"] = tokens.session_totals(conn, req.session_key)
    return result
