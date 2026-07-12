import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ChatMessage, Persona } from "../types";
import { RichText } from "./TraceChips";

interface Scope { type: "company" | "project"; id: number }

export function ChatPanel({ scope, personas, scopeName }: {
  scope: Scope | null;
  personas: Persona[];
  scopeName?: string;
}) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [web, setWeb] = useState(false);
  const [mcp, setMcp] = useState(false);
  const [personaId, setPersonaId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadSession = useCallback(async () => {
    if (!scope) return;
    const sessions = await api.listSessions(scope.type, scope.id);
    if (sessions.length > 0) {
      setSessionId(sessions[0].id);
      setPersonaId(sessions[0].persona_id);
      setMessages(await api.listMessages(sessions[0].id));
    } else {
      setSessionId(null);
      setMessages([]);
      setPersonaId(null);
    }
  }, [scope?.type, scope?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setError("");
    loadSession().catch(() => {});
  }, [loadSession]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, busy]);

  if (!scope) {
    return (
      <div className="chat-head">
        <span className="chat-title">Chat</span>
        <p className="muted small">
          Open a company dashboard or a project to chat about it here. Answers are
          anchored in the ingested reports, with optional web search and MCP tools.
        </p>
      </div>
    );
  }

  const send = async () => {
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    setError("");
    setText("");
    // optimistic user bubble
    setMessages((m) => [...m, { id: -1, role: "user", content,
      citations: [], tool_calls: [] }]);
    try {
      let sid = sessionId;
      if (!sid) {
        const session = await api.createSession(scope.type, scope.id, personaId);
        sid = session.id;
        setSessionId(sid);
      }
      await api.sendMessage(sid, content, web, mcp);
      setMessages(await api.listMessages(sid));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const changePersona = async (value: string) => {
    const pid = value ? Number(value) : null;
    setPersonaId(pid);
    if (sessionId) await api.setSessionPersona(sessionId, pid);
  };

  return (
    <>
      <div className="chat-head">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span className="chat-title">
            Chat · {scopeName ?? `${scope.type} #${scope.id}`}
          </span>
          <button className="small" title="Start a fresh conversation"
            style={{ padding: "2px 8px" }}
            onClick={async () => {
              const session = await api.createSession(scope.type, scope.id, personaId);
              setSessionId(session.id);
              setMessages([]);
            }}>New</button>
        </div>
        <div className="row" style={{ marginTop: 6 }}>
          <select style={{ width: "100%" }} value={personaId ?? ""}
            title="Persona for this conversation"
            onChange={(e) => changePersona(e.target.value)}>
            <option value="">No persona</option>
            {personas.filter((p) => p.enabled).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="chat-msgs" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="muted small">
            Ask anything about the ingested reports — e.g. “What are the main
            risks?” or “How did margins evolve?”
          </p>
        )}
        {messages.map((m, i) => (
          <div key={m.id > 0 ? m.id : `tmp${i}`} className={`msg ${m.role}`}>
            <div className="bubble"><MessageBody message={m} /></div>
            {m.role === "assistant" && m.tool_calls.length > 0 && (
              <div className="muted small" style={{ marginTop: 2 }}>
                tools: {m.tool_calls.map((t) => t.name).join(", ")}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="msg assistant">
            <div className="bubble muted">Thinking…</div>
          </div>
        )}
        {error && <p className="error-text small">{error}</p>}
      </div>

      <div className="chat-input">
        <div className="chat-toggles">
          <label title="Allow cached web searches">
            <input type="checkbox" checked={web}
              onChange={(e) => setWeb(e.target.checked)} /> Web search
          </label>
          <label title="Allow configured MCP server tools">
            <input type="checkbox" checked={mcp}
              onChange={(e) => setMcp(e.target.checked)} /> MCP tools
          </label>
        </div>
        <textarea value={text} placeholder="Ask about this company…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }} />
        <button className="primary" disabled={busy || !text.trim()} onClick={send}>
          Send
        </button>
      </div>
    </>
  );
}

/** Renders message text with [chunk:N]/[fact:N] markers as clickable chips. */
function MessageBody({ message }: { message: ChatMessage }) {
  return <RichText text={message.content} />;
}
