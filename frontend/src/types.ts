export interface Report {
  id: number;
  fiscal_year: number | null;
  form: string | null;
  source_url: string | null;
  format: string | null;
  status: string;
  error: string | null;
  filed_at: string | null;
}

export interface Company {
  id: number;
  name: string;
  ticker: string | null;
  cik: string | null;
  source_mode: string;
  status: string;
  error: string | null;
  saved: number;
  created_at: string;
  ready_reports?: number;
  reports?: Report[];
}

export interface FactMetric {
  metric: string;
  label: string;
  unit: string | null;
  source_kind: string;
  values: Record<string, number | null>;
  fact_ids: Record<string, number>;
}

export interface FactPivot {
  years: number[];
  metrics: FactMetric[];
}

export interface Cited {
  citations?: string[];
}

export interface AnalysisContent {
  executive_summary?: string;
  business_overview?: string;
  financial_highlights?: ({ statement: string } & Cited)[];
  trends?: ({ metric: string; direction: string; comment: string } & Cited)[];
  risks?: ({ title: string; summary: string } & Cited)[];
  outlook?: string;
  error?: string;
}

export interface Analysis {
  id: number;
  kind: string;
  persona_id: number | null;
  provider: string | null;
  model: string | null;
  created_at: string;
  content: AnalysisContent;
}

export interface Persona {
  id: number;
  name: string;
  description: string | null;
  system_prompt: string;
  enabled: number;
  web_enabled: number;
  mcp_enabled: number;
  builtin: number;
}

export interface ChatSession {
  id: number;
  scope_type: string;
  scope_id: number;
  persona_id: number | null;
  title: string | null;
}

export interface Citation {
  kind: "chunk" | "fact";
  id: number;
}

export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  citations: Citation[];
  tool_calls: { name: string; arguments: unknown }[];
}

export interface TokenTotals {
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export interface TokenReport {
  session: TokenTotals;
  all_time: TokenTotals;
  recent: {
    id: number;
    provider: string;
    model: string | null;
    input_tokens: number;
    output_tokens: number;
    context: string | null;
  }[];
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  company_count?: number;
  companies?: Company[];
  metrics?: ProjectMetric[];
}

export interface ProjectMetric {
  id: number;
  name: string;
  description: string | null;
  formula: string;
  results: Record<string, { value: number | null; fiscal_year?: number; error?: string }>;
  trace: Record<string, unknown>;
}

export interface Comparison {
  companies: { id: number; name: string; ticker: string | null }[];
  years: number[];
  rows: {
    metric: string;
    label: string;
    unit: string | null;
    values: Record<string, Record<string, number | null>>;
    fact_ids: Record<string, Record<string, number>>;
  }[];
}

export interface McpServer {
  id: number;
  name: string;
  transport: string;
  command: string | null;
  url: string | null;
  args_json: string | null;
  enabled: number;
}

export interface Trace {
  kind: string;
  [key: string]: unknown;
}

export type Settings = Record<string, string>;
