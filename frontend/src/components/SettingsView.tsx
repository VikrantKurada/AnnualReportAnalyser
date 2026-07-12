import { useEffect, useState } from "react";
import { api } from "../api";
import type { McpServer, Persona, Settings } from "../types";

export function SettingsView({ personas, onPersonasChange, onSettingsChange }: {
  personas: Persona[];
  onPersonasChange: () => void;
  onSettingsChange: () => void;
}) {
  return (
    <div>
      <h2 className="page-title">Settings</h2>
      <ProviderSettings onSettingsChange={onSettingsChange} />
      <PersonaSettings personas={personas} onChange={onPersonasChange} />
      <McpSettings />
    </div>
  );
}

function ProviderSettings({ onSettingsChange }: { onSettingsChange: () => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState("");

  useEffect(() => { api.getSettings().then(setSettings).catch(() => {}); }, []);
  if (!settings) return null;

  const set = (key: string, value: string) =>
    setSettings({ ...settings, [key]: value });

  const save = async () => {
    setSaving(true);
    try {
      setSettings(await api.putSettings(settings));
      onSettingsChange();
      setTestResult("Saved.");
    } catch (e) {
      setTestResult(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTestResult("Testing…");
    const r = await api.testProvider();
    setTestResult(r.ok
      ? `OK — ${r.provider} · ${r.model} replied: ${r.reply}`
      : `Failed: ${r.error}`);
  };

  const provider = settings.llm_provider;

  return (
    <div className="card">
      <h3>LLM provider</h3>
      <div className="form-grid">
        <label>Chat provider</label>
        <select value={provider} onChange={(e) => set("llm_provider", e.target.value)}>
          <option value="ollama">Ollama (local)</option>
          <option value="anthropic">Claude API (Anthropic)</option>
          <option value="openai">OpenAI</option>
          <option value="nvidia">NVIDIA API</option>
        </select>

        {provider !== "anthropic" && (
          <>
            <label>Chat model</label>
            <input value={settings.llm_model}
              onChange={(e) => set("llm_model", e.target.value)} />
          </>
        )}

        {provider === "ollama" && (
          <>
            <label>Ollama base URL</label>
            <input value={settings.ollama_base_url}
              onChange={(e) => set("ollama_base_url", e.target.value)} />
          </>
        )}
        {provider === "anthropic" && (
          <>
            <label>Anthropic model</label>
            <input value={settings.anthropic_model}
              onChange={(e) => set("anthropic_model", e.target.value)} />
            <label>Anthropic API key</label>
            <input type="password" value={settings.anthropic_api_key}
              onChange={(e) => set("anthropic_api_key", e.target.value)} />
          </>
        )}
        {provider === "openai" && (
          <>
            <label>OpenAI base URL</label>
            <input value={settings.openai_base_url}
              onChange={(e) => set("openai_base_url", e.target.value)} />
            <label>OpenAI API key</label>
            <input type="password" value={settings.openai_api_key}
              onChange={(e) => set("openai_api_key", e.target.value)} />
          </>
        )}
        {provider === "nvidia" && (
          <>
            <label>NVIDIA base URL</label>
            <input value={settings.nvidia_base_url}
              onChange={(e) => set("nvidia_base_url", e.target.value)} />
            <label>NVIDIA API key</label>
            <input type="password" value={settings.nvidia_api_key}
              onChange={(e) => set("nvidia_api_key", e.target.value)} />
          </>
        )}

        <label>Embeddings provider</label>
        <select value={settings.embed_provider}
          onChange={(e) => set("embed_provider", e.target.value)}>
          <option value="ollama">Ollama (local)</option>
          <option value="openai">OpenAI</option>
          <option value="nvidia">NVIDIA API</option>
        </select>
        <label>Embeddings model</label>
        <input value={settings.embed_model}
          onChange={(e) => set("embed_model", e.target.value)} />

        <label>Web cache TTL (seconds)</label>
        <input value={settings.search_cache_ttl}
          onChange={(e) => set("search_cache_ttl", e.target.value)} />
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" disabled={saving} onClick={save}>Save</button>
        <button onClick={test}>Test connection</button>
        {testResult && <span className="small muted">{testResult}</span>}
      </div>
    </div>
  );
}

const EMPTY_PERSONA: Partial<Persona> = {
  name: "", description: "", system_prompt: "", enabled: 1,
  web_enabled: 1, mcp_enabled: 1,
};

function PersonaSettings({ personas, onChange }: {
  personas: Persona[];
  onChange: () => void;
}) {
  const [editing, setEditing] = useState<Partial<Persona> | null>(null);

  const save = async () => {
    if (!editing?.name || !editing.system_prompt) return;
    const payload = {
      name: editing.name, description: editing.description ?? "",
      system_prompt: editing.system_prompt,
      enabled: Boolean(editing.enabled), web_enabled: Boolean(editing.web_enabled),
      mcp_enabled: Boolean(editing.mcp_enabled),
    };
    if (editing.id) {
      await api.updatePersona(editing.id, payload);
    } else {
      await api.createPersona(payload);
    }
    setEditing(null);
    onChange();
  };

  return (
    <div className="card">
      <h3>Personas</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        Personas are optional lenses (e.g. CFO, Wall Street Analyst) applied to
        analyses and chats. Each can be allowed or denied web search and MCP tools.
      </p>
      <div className="scroll-x">
        <table className="data">
          <thead>
            <tr><th>Persona</th><th>Enabled</th><th>Web</th><th>MCP</th><th></th></tr>
          </thead>
          <tbody>
            {personas.map((p) => (
              <tr key={p.id}>
                <td title={p.description ?? ""}>{p.name}{p.builtin ? " ·" : ""}
                  {p.builtin ? <span className="muted small"> built-in</span> : ""}</td>
                <td>{p.enabled ? "✓" : "–"}</td>
                <td>{p.web_enabled ? "✓" : "–"}</td>
                <td>{p.mcp_enabled ? "✓" : "–"}</td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end" }}>
                    <button className="small" style={{ padding: "2px 8px" }}
                      onClick={() => setEditing({ ...p })}>Edit</button>
                    <button className="small" style={{ padding: "2px 8px" }}
                      onClick={async () => {
                        if (confirm(`Delete persona ${p.name}?`)) {
                          await api.deletePersona(p.id);
                          onChange();
                        }
                      }}>✕</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button onClick={() => setEditing({ ...EMPTY_PERSONA })}>+ Add persona</button>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editing.id ? `Edit ${editing.name}` : "New persona"}</h3>
            <div className="form-grid" style={{ gridTemplateColumns: "120px 1fr" }}>
              <label>Name</label>
              <input value={editing.name ?? ""}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
              <label>Description</label>
              <input value={editing.description ?? ""}
                onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
              <label>System prompt</label>
              <textarea rows={6} value={editing.system_prompt ?? ""}
                onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })} />
            </div>
            <div className="chat-toggles" style={{ marginTop: 10 }}>
              {(["enabled", "web_enabled", "mcp_enabled"] as const).map((key) => (
                <label key={key}>
                  <input type="checkbox" checked={Boolean(editing[key])}
                    onChange={(e) =>
                      setEditing({ ...editing, [key]: e.target.checked ? 1 : 0 })} />
                  {key === "enabled" ? "Enabled"
                    : key === "web_enabled" ? "Web search allowed" : "MCP allowed"}
                </label>
              ))}
            </div>
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
              <button onClick={() => setEditing(null)}>Cancel</button>
              <button className="primary" onClick={save}
                disabled={!editing.name || !editing.system_prompt}>Save persona</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function McpSettings() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [draft, setDraft] = useState({ name: "", transport: "stdio",
    command: "", url: "", args: "" });
  const [toolInfo, setToolInfo] = useState("");
  const [error, setError] = useState("");

  const refresh = () => api.listMcpServers().then(setServers).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const add = async () => {
    setError("");
    try {
      await api.createMcpServer({
        name: draft.name, transport: draft.transport,
        command: draft.transport === "stdio" ? draft.command : null,
        url: draft.transport === "http" ? draft.url : null,
        args_json: JSON.stringify(
          draft.args.trim() ? draft.args.trim().split(/\s+/) : []),
      });
      setDraft({ name: "", transport: "stdio", command: "", url: "", args: "" });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="card">
      <h3>MCP servers</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        Connected MCP servers expose their tools to chats, projects, and personas
        (when the “MCP tools” toggle is on).
      </p>
      {servers.length > 0 && (
        <div className="scroll-x" style={{ marginBottom: 10 }}>
          <table className="data">
            <thead>
              <tr><th>Name</th><th>Transport</th><th>Target</th><th></th></tr>
            </thead>
            <tbody>
              {servers.map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td>{s.transport}</td>
                  <td><code className="small">{s.command ?? s.url}</code></td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="small" style={{ padding: "2px 8px" }}
                        onClick={async () => {
                          setToolInfo("Listing tools…");
                          const r = await api.mcpServerTools(s.id);
                          setToolInfo(r.ok
                            ? `${s.name}: ${r.tools.map((t) => t.name).join(", ") || "no tools"}`
                            : `${s.name}: ${r.error}`);
                        }}>Tools</button>
                      <button className="small" style={{ padding: "2px 8px" }}
                        onClick={async () => {
                          await api.deleteMcpServer(s.id);
                          refresh();
                        }}>✕</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {toolInfo && <p className="small muted">{toolInfo}</p>}
      <div className="row">
        <input placeholder="Name" style={{ width: 120 }} value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <select value={draft.transport}
          onChange={(e) => setDraft({ ...draft, transport: e.target.value })}>
          <option value="stdio">stdio</option>
          <option value="http">http</option>
        </select>
        {draft.transport === "stdio" ? (
          <>
            <input placeholder="Command (e.g. npx)" style={{ width: 160 }}
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })} />
            <input placeholder="Args (space separated)" style={{ flex: 1, minWidth: 180 }}
              value={draft.args}
              onChange={(e) => setDraft({ ...draft, args: e.target.value })} />
          </>
        ) : (
          <input placeholder="URL (e.g. http://localhost:3001/mcp)"
            style={{ flex: 1, minWidth: 220 }} value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })} />
        )}
        <button className="primary" disabled={!draft.name} onClick={add}>Add</button>
      </div>
      {error && <p className="error-text small">{error}</p>}
    </div>
  );
}
