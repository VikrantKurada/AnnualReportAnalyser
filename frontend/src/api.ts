import type {
  Analysis, ChatMessage, ChatSession, Company, Comparison, FactPivot,
  McpServer, Persona, Project, ProjectMetric, Settings, TokenReport, Trace,
  Valuation,
} from "./types";
import type { DashboardConfig } from "./metricCatalog";

export interface PersonaPayload {
  name: string;
  description: string;
  system_prompt: string;
  enabled: boolean;
  web_enabled: boolean;
  mcp_enabled: boolean;
}

export function sessionKey(): string {
  let key = sessionStorage.getItem("ara_session_key");
  if (!key) {
    key = crypto.randomUUID();
    sessionStorage.setItem("ara_session_key", key);
  }
  return key;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b);
const put = <T,>(p: string, b?: unknown) => request<T>("PUT", p, b);
const del = <T,>(p: string) => request<T>("DELETE", p);

export const api = {
  // companies
  fetchCompany: (name: string, source_mode: string) =>
    post<Company>("/api/companies/fetch", { name, source_mode }),
  listCompanies: () => get<Company[]>("/api/companies"),
  getCompany: (id: number) => get<Company>(`/api/companies/${id}`),
  saveCompany: (id: number, saved: boolean) =>
    post<{ ok: boolean }>(`/api/companies/${id}/save`, { saved }),
  deleteCompany: (id: number) => del<{ ok: boolean }>(`/api/companies/${id}`),
  companyFacts: (id: number) => get<FactPivot>(`/api/companies/${id}/facts`),
  analyzeCompany: (id: number, persona_id: number | null) =>
    post<{ status: string }>(`/api/companies/${id}/analyze`,
      { persona_id, session_key: sessionKey() }),
  latestAnalysis: (id: number, personaId: number | null) =>
    get<{ analysis: Analysis | null }>(
      `/api/companies/${id}/analysis${personaId ? `?persona_id=${personaId}` : ""}`),
  getTrace: (kind: string, id: number) => get<Trace>(`/api/trace/${kind}/${id}`),
  getValuation: (id: number) => get<Valuation>(`/api/companies/${id}/valuation`),
  getDashboardConfig: async (): Promise<DashboardConfig> => {
    const s = await get<Record<string, unknown>>("/api/settings");
    return (s.dashboard_config as DashboardConfig) ?? {};
  },
  putDashboardConfig: (config: DashboardConfig) =>
    put<Settings>("/api/settings", { dashboard_config: config } as unknown as Settings),

  // chat
  createSession: (scope_type: string, scope_id: number, persona_id: number | null) =>
    post<ChatSession>("/api/chat/sessions", { scope_type, scope_id, persona_id }),
  listSessions: (scope_type: string, scope_id: number) =>
    get<ChatSession[]>(`/api/chat/sessions?scope_type=${scope_type}&scope_id=${scope_id}`),
  setSessionPersona: (id: number, personaId: number | null) =>
    put<{ ok: boolean }>(`/api/chat/sessions/${id}/persona${
      personaId ? `?persona_id=${personaId}` : ""}`),
  listMessages: (id: number) => get<ChatMessage[]>(`/api/chat/sessions/${id}/messages`),
  sendMessage: (id: number, text: string, web: boolean, mcp: boolean) =>
    post<{ content: string; citations: { kind: "chunk" | "fact"; id: number }[] }>(
      `/api/chat/sessions/${id}/messages`,
      { text, session_key: sessionKey(), web_enabled: web, mcp_enabled: mcp }),

  // projects
  createProject: (name: string, description: string) =>
    post<Project>("/api/projects", { name, description }),
  listProjects: () => get<Project[]>("/api/projects"),
  getProject: (id: number) => get<Project>(`/api/projects/${id}`),
  deleteProject: (id: number) => del<{ ok: boolean }>(`/api/projects/${id}`),
  addProjectCompany: (pid: number, company_id: number) =>
    post<{ ok: boolean }>(`/api/projects/${pid}/companies`, { company_id }),
  removeProjectCompany: (pid: number, cid: number) =>
    del<{ ok: boolean }>(`/api/projects/${pid}/companies/${cid}`),
  compareProject: (pid: number) => get<Comparison>(`/api/projects/${pid}/compare`),
  addMetric: (pid: number, name: string, description: string, formula: string) =>
    post<ProjectMetric[]>(`/api/projects/${pid}/metrics`, { name, description, formula }),
  deleteMetric: (pid: number, mid: number) =>
    del<{ ok: boolean }>(`/api/projects/${pid}/metrics/${mid}`),
  suggestMetric: (pid: number, prompt: string) =>
    post<{ name: string; description: string; formula: string }>(
      `/api/projects/${pid}/metrics/suggest`, { prompt, session_key: sessionKey() }),
  analyzeProject: (pid: number, persona_id: number | null) =>
    post<{ status: string }>(`/api/projects/${pid}/analyze`,
      { persona_id, session_key: sessionKey() }),
  latestProjectAnalysis: (pid: number) =>
    get<{ analysis: Analysis | null }>(`/api/projects/${pid}/analysis`),

  // admin
  listPersonas: () => get<Persona[]>("/api/personas"),
  createPersona: (p: PersonaPayload) => post<Persona>("/api/personas", p),
  updatePersona: (id: number, p: PersonaPayload) =>
    put<Persona>(`/api/personas/${id}`, p),
  deletePersona: (id: number) => del<{ ok: boolean }>(`/api/personas/${id}`),
  getSettings: () => get<Settings>("/api/settings"),
  putSettings: (values: Settings) => put<Settings>("/api/settings", values),
  testProvider: () =>
    get<{ ok: boolean; provider?: string; model?: string; reply?: string; error?: string }>(
      "/api/settings/providers/test"),
  getTokens: () => get<TokenReport>(`/api/tokens?session_key=${sessionKey()}`),
  listMcpServers: () => get<McpServer[]>("/api/mcp/servers"),
  createMcpServer: (s: Partial<McpServer>) => post<McpServer>("/api/mcp/servers", s),
  deleteMcpServer: (id: number) => del<{ ok: boolean }>(`/api/mcp/servers/${id}`),
  mcpServerTools: (id: number) =>
    get<{ ok: boolean; tools: { name: string; description: string }[]; error?: string }>(
      `/api/mcp/servers/${id}/tools`),
};

export function formatValue(value: number | null, unit: string | null): string {
  if (value === null || value === undefined) return "–";
  if (unit === "ratio") {
    return `${(value * 100).toFixed(1)}%`;
  }
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(value / 1e3).toFixed(1)}K`;
  return abs >= 100 ? value.toFixed(0) : value.toFixed(2);
}
