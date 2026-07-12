# Annual Report Analyser — Design

Date: 2026-07-12
Status: Approved

## Goal

A local web application that fetches a company's last three annual reports, parses them
into structured text/tables/numbers, stores everything persistently, runs LLM analysis,
and presents the results on a dashboard with an anchored chat panel. Supports company
profiles, comparison projects, configurable LLM providers, personas, web search with
caching, MCP integration, full traceability of numbers, and session token tracking.

## Decisions (from brainstorming)

- **Stack:** FastAPI (Python) backend + React/Vite/TypeScript frontend. Single process:
  FastAPI serves the API and the built frontend at `http://localhost:8000`.
- **Markets:** user chooses per company between **US-listed (SEC EDGAR)** and
  **Global best-effort (web search for IR-page PDFs)**.
- **Primary LLM for development/testing:** Ollama (local). All of Ollama, Anthropic,
  OpenAI, and NVIDIA are implemented and configurable.
- **Storage:** one SQLite file (`data/app.db`). Embeddings stored as float32 BLOBs;
  vector search is brute-force cosine via numpy (fine at this scale; avoids native
  SQLite extensions on Windows).
- **US numbers:** SEC XBRL company-facts API is the primary source of financial facts;
  document tables are the fallback. Global path relies on parsed PDF tables.

## Architecture

### Ingestion pipeline

1. User enters company name and picks source mode.
2. **EDGAR path:** resolve ticker/name → CIK (`company_tickers.json`), list 10-K filings
   via the submissions API, download the primary HTML document for the last three
   filings, and pull XBRL company facts for clean numbers.
3. **Global path:** cached DuckDuckGo search for `<company> annual report <year>`
   (+ `filetype:pdf` heuristics), rank candidate PDFs, download the last three, parse
   with `pdfplumber` (text + tables).
4. Both converge to a normalized form: sectioned text chunks, tables as JSON, and
   financial facts — each stamped with origin (URL, page/section, XBRL tag, table cell).
5. Chunks are embedded via the configurable embeddings provider (default: Ollama
   `nomic-embed-text`) and stored.

### Storage (SQLite, persists across sessions)

Tables: `companies`, `reports`, `chunks` (text + embedding blob), `doc_tables`,
`facts` (metric, fiscal year, value, unit, source kind + ref), `analyses`
(content JSON + trace + persona + model), `chat_sessions`, `chat_messages`
(with citations), `personas`, `projects`, `project_companies`, `project_metrics`
(definition + results + trace), `web_cache` (query/url hash → content, TTL),
`settings`, `token_usage`.

### LLM provider layer

`LLMProvider` interface: `chat(messages, tools=None) -> (message, usage)` and
`embed(texts) -> vectors`. Adapters:

- **Ollama** — local HTTP `http://localhost:11434`, supports tool calling on capable models.
- **Anthropic** — Claude API.
- **OpenAI** — Chat Completions.
- **NVIDIA** — OpenAI-compatible endpoint (`integrate.api.nvidia.com`).

Provider, model, base URL, and API keys are editable in the Settings UI, stored in the
`settings` table. Every call records input/output tokens into `token_usage` with a
session id; the UI header shows live session totals.

### Analysis & traceability

- A structured analysis pass runs over key sections + facts and produces dashboard JSON
  (summary, highlights, trends, risks, ratios) where every claim/number carries
  citations (chunk ids / fact ids).
- Derived ratios/metrics are computed **in Python** from stored facts, never by the LLM;
  the formula and input fact ids are stored alongside the result.
- The dashboard renders a source badge on every number; clicking opens the trace
  (XBRL tag / table cell / text excerpt, report, and link).

### Chat, personas, projects, MCP

- Chat is tool-enabled: document retrieval (vector search over chunks), toggleable web
  search (through the shared cache), and tools from user-configured external MCP servers
  (backend acts as MCP client via the `mcp` Python SDK).
- Personas are optional system-prompt overlays with the same web/MCP access. CFO and
  Wall Street Analyst ship as editable defaults; users can add their own. Selectable in
  chat and in analysis (persona-flavored analyses are stored separately).
- Projects group saved company profiles for comparison; users can define new derived
  comparison metrics (LLM-assisted definition, Python-computed where numeric); results
  persist to the DB with traces.

### Web search caching

All web searches and fetched pages go through a cache layer keyed by query/URL hash in
`web_cache`, with TTL (24 h for searches; filings/PDF downloads cached indefinitely on
disk under `data/files/`).

### Frontend

React + Vite + TypeScript, professional light minimal design. Fixed header (company
selector, session token tracker, settings). Left pane: dashboard, 75 % width, its own
vertical scroll; wide tables/charts scroll horizontally inside their containers, never
the page. Right pane: chat, ~20 % width, own scroll. Views: Companies (search/fetch +
saved profiles), Company Dashboard, Projects, Settings. Charts via Recharts.

### Testing

pytest for core logic: EDGAR resolution (mocked HTTP), parsing/normalization, ratio
computation, cache TTL behavior, provider adapters (mocked), token accounting. Manual
end-to-end smoke test against local Ollama.

## Out of scope (YAGNI)

- Multi-user auth, cloud deployment, background job queues (ingestion runs as async
  tasks in-process), quarterly reports, non-annual filings, XBRL parsing for non-US
  filings.
