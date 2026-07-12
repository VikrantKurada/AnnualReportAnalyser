# Annual Report Analyser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Local web app that fetches a company's last 3 annual reports (SEC EDGAR or global web), parses them into text/tables/facts stored in SQLite, runs traceable LLM analysis, and serves a 75/20 dashboard + chat UI with personas, projects, MCP, web-search caching, and token tracking.

**Architecture:** FastAPI backend (Python 3.14) serving API + built React frontend on `http://localhost:8000`. Single SQLite file `data/app.db` for everything including embeddings (float32 BLOBs, numpy cosine search). Provider-agnostic LLM layer over raw HTTP (Ollama default; Anthropic/OpenAI/NVIDIA adapters). Ingestion converges EDGAR HTML+XBRL and global PDFs into one normalized store.

**Tech Stack:** fastapi, uvicorn, httpx, beautifulsoup4, pdfplumber, numpy, ddgs, mcp, pytest, pytest-asyncio · React 18 + Vite + TypeScript, recharts.

**Environment verified:** Python 3.14.0, Node v24.11.1, Ollama running with `glm-4.7-flash:latest` (chat, tools) and `nomic-embed-text` (embeddings).

**Execution note:** run from repo root `D:\Projects\AnnualReportAnalyser`. Backend venv at `.venv`; use `.venv\Scripts\python -m pytest`. Commit after every task.

---

### Task 1: Scaffolding

**Files:** Create `.gitignore`, `backend/requirements.txt`, `backend/app/__init__.py`, `backend/tests/__init__.py`, `backend/pytest.ini`; scaffold `frontend/` with Vite react-ts.

1. `.gitignore`: `.venv/`, `node_modules/`, `data/`, `dist/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.
2. `python -m venv .venv` then `.venv\Scripts\pip install fastapi uvicorn httpx beautifulsoup4 pdfplumber numpy ddgs mcp pytest pytest-asyncio` (if any package lacks a 3.14 wheel, note fallback: `lxml`→use `html.parser`; pin nothing unless forced). Freeze to `backend/requirements.txt`.
3. `npm create vite@latest frontend -- --template react-ts`, `npm install` + `npm install recharts`.
4. Smoke test `backend/tests/test_smoke.py::test_imports` imports fastapi/httpx/numpy/pdfplumber/bs4. Run `pytest`, expect PASS. Commit.

### Task 2: Database layer

**Files:** Create `backend/app/db.py`, `backend/app/schema.sql`, `backend/tests/test_db.py`.

`db.py`: `get_conn(path)` (sqlite3, `Row` factory, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`), `init_db(conn)` executes `schema.sql` (idempotent `CREATE TABLE IF NOT EXISTS`), tiny helpers `insert(conn, table, dict)->id`, `query(conn, sql, params)->list[dict]`. DB path from env `ARA_DB_PATH` default `data/app.db`.

`schema.sql` tables (all with `id INTEGER PRIMARY KEY AUTOINCREMENT` unless noted):

- `companies(name, ticker, cik, source_mode, exchange, profile_json, saved INTEGER DEFAULT 0, created_at)`
- `reports(company_id→companies, fiscal_year INTEGER, form, source_url, local_path, format, status, error, filed_at, created_at)`
- `chunks(report_id→reports, section, seq INTEGER, text, page, embedding BLOB, embed_model)`
- `doc_tables(report_id→reports, section, page, caption, data_json)`
- `facts(company_id→companies, report_id, fiscal_year INTEGER, metric, label, value REAL, unit, source_kind, source_ref, UNIQUE(company_id,fiscal_year,metric,source_kind))`
- `analyses(company_id, project_id, persona_id, kind, content_json, trace_json, provider, model, created_at)`
- `personas(name, description, system_prompt, enabled INTEGER DEFAULT 1, web_enabled INTEGER DEFAULT 1, mcp_enabled INTEGER DEFAULT 1, builtin INTEGER DEFAULT 0)`
- `projects(name, description, created_at)` · `project_companies(project_id, company_id, UNIQUE both)`
- `project_metrics(project_id, name, description, formula, results_json, trace_json, created_at)`
- `chat_sessions(scope_type, scope_id, persona_id, title, created_at)` · `chat_messages(session_id, role, content, citations_json, tool_calls_json, created_at)`
- `web_cache(key TEXT PRIMARY KEY, kind, url, content, fetched_at REAL, ttl REAL)`
- `settings(key TEXT PRIMARY KEY, value TEXT)`
- `token_usage(session_key, provider, model, input_tokens INTEGER, output_tokens INTEGER, context, created_at REAL)`
- `mcp_servers(name, transport, command, url, args_json, enabled INTEGER DEFAULT 1)`

Tests: init idempotent; insert/query roundtrip; FK cascade on reports→chunks (use `ON DELETE CASCADE`). TDD: write tests first, fail, implement, pass, commit.

### Task 3: Settings + token tracking

**Files:** Create `backend/app/settings.py`, `backend/app/tokens.py`, tests.

`settings.py`: `get_setting/set_setting/all_settings` with JSON values; defaults dict: `llm_provider=ollama`, `llm_model=glm-4.7-flash:latest`, `embed_provider=ollama`, `embed_model=nomic-embed-text`, `ollama_base_url=http://localhost:11434`, `anthropic_api_key=""`, `openai_api_key=""`, `openai_base_url=https://api.openai.com/v1`, `nvidia_api_key=""`, `nvidia_base_url=https://integrate.api.nvidia.com/v1`, `anthropic_model=claude-sonnet-5`, `search_cache_ttl=86400`. `masked_settings()` masks `*_api_key` for the API.
`tokens.py`: `record_usage(conn, session_key, provider, model, in_toks, out_toks, context)`, `session_totals(conn, session_key)` and `totals_all(conn)`. Tests, commit.

### Task 4: LLM provider layer

**Files:** Create `backend/app/providers/__init__.py`, `base.py`, `ollama.py`, `openai_compat.py`, `anthropic.py`, `registry.py`; test `backend/tests/test_providers.py`.

`base.py`:

```python
@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[dict]      # [{"id","name","arguments":dict}]
    input_tokens: int
    output_tokens: int
    raw: dict

class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             json_mode: bool = False) -> ChatResult: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Messages use OpenAI-style dicts (`role`, `content`, optional `tool_calls`, `tool_call_id`). Tools use OpenAI function schema; adapters translate.

- `ollama.py`: POST `{base}/api/chat` (`stream:false`, `tools`, `format:"json"` when json_mode); tokens from `prompt_eval_count`/`eval_count`. `embed`: POST `/api/embed` `{"model","input":texts}`.
- `openai_compat.py`: `/chat/completions` + `/embeddings`; serves both OpenAI and NVIDIA (different base_url/key). `response_format={"type":"json_object"}` when json_mode. Tokens from `usage`.
- `anthropic.py`: POST `https://api.anthropic.com/v1/messages`, `anthropic-version: 2023-06-01`; translate tools to Anthropic `input_schema` form and back; system message extracted to `system=`. `embed` raises `NotImplementedError` (registry routes embeddings to embed_provider).
- `registry.py`: `get_llm(conn)` and `get_embedder(conn)` build the adapter from settings; wraps `chat` so every call auto-records token usage via `tokens.record_usage` (session_key passed in).

Tests: mock `httpx.Client` transport (`httpx.MockTransport`); assert request shape + response parsing + token extraction for each adapter; registry picks correct class. Commit.

### Task 5: Web cache + search

**Files:** Create `backend/app/web.py`, test.

- `cache_get(conn,key)` / `cache_put(conn,key,kind,url,content,ttl)`; expiry by `fetched_at+ttl < now`; `ttl<=0` = forever.
- `fetch_url(conn, url, ttl=None, binary=False)` — httpx GET with browser-ish UA, 30s timeout; binary content saved under `data/files/<sha1>.<ext>`, cache stores path; text cached inline.
- `web_search(conn, query, max_results=8)` — `ddgs` `DDGS().text(query, max_results=...)`, normalized to `[{"title","url","snippet"}]`, cached with `search_cache_ttl`.

Tests: cache roundtrip + TTL expiry with monkeypatched clock; `web_search` with mocked DDGS returns and caches. Commit.

### Task 6: Document parsing → normalized chunks/tables

**Files:** Create `backend/app/ingest/__init__.py`, `parse_html.py`, `parse_pdf.py`, `chunking.py`; tests + fixtures `backend/tests/fixtures/mini_10k.html`, generated small PDF.

- `parse_html.parse(html) -> ParsedDoc{sections:[{title, text}], tables:[{caption, rows}]}`: strip script/style/XBRL `ix:` noise, walk headings (`h1-h4`, bold-only paragraphs matching `Item \d+`), accumulate text per section; `<table>` → rows of cell strings, caption = nearest preceding heading.
- `parse_pdf.parse(path) -> ParsedDoc` with `page` on sections/tables via pdfplumber `extract_text()` + `extract_tables()`; section detection: ALL-CAPS/numbered-heading heuristics, fallback one section per page-range.
- `chunking.chunk_sections(sections, target=1800 chars, overlap=200) -> [{"section","seq","text","page"}]` splitting on paragraph boundaries.

Tests: fixture HTML yields expected sections/tables; PDF fixture (generate in test via pdfplumber-readable simple PDF using `fpdf2`? NO — avoid extra dep: commit a tiny static PDF fixture, or build one with pure-python minimal PDF bytes in the test) — simplest: create fixture PDF once via a helper script with pdfplumber's sibling lib not needed; a hand-written minimal PDF with one text object is enough for `extract_text`. Chunker: respects target size, keeps section labels, overlap present. Commit.

### Task 7: EDGAR client

**Files:** Create `backend/app/ingest/edgar.py`, test (all HTTP mocked through `web.fetch_url`).

Constants: UA `AnnualReportAnalyser/1.0 (vikrant.kurada@gmail.com)` (SEC requires contact UA).

- `resolve_company(conn, query)` → `https://www.sec.gov/files/company_tickers.json` (cache ttl 7d); match by ticker exact (case-insens) then name substring; returns `{cik(10-digit str), ticker, name}` or top-5 candidates.
- `list_annual_filings(conn, cik, n=3)` → `https://data.sec.gov/submissions/CIK{cik}.json`; filter `form=="10-K"` (accept `10-K/A` only if no 10-K for that FY); build doc URL `https://www.sec.gov/Archives/edgar/data/{int_cik}/{accession_nodash}/{primaryDocument}`; return `[{fiscal_year(from reportDate), filed_at, url, form}]` newest 3.
- `company_facts(conn, cik)` → `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`; extract us-gaap concepts into facts rows: map `{Revenues|RevenueFromContractWithCustomerExcludingAssessedTax→revenue, NetIncomeLoss→net_income, Assets→total_assets, Liabilities→total_liabilities, StockholdersEquity→equity, CashAndCashEquivalentsAtCarryingValue→cash, OperatingIncomeLoss→operating_income, EarningsPerShareDiluted→eps_diluted, CommonStockSharesOutstanding→shares_outstanding, LiabilitiesCurrent→current_liabilities, AssetsCurrent→current_assets, LongTermDebtNoncurrent→long_term_debt, OperatingCashFlow: NetCashProvidedByUsedInOperatingActivities→operating_cash_flow}`; keep only 10-K annual datapoints (`form=="10-K"`, `fp=="FY"`), pick USD (or `USD/shares`/`shares`), dedupe per fy by latest `end`; `source_kind="xbrl"`, `source_ref=json{"tag":...,"accn":...,"end":...}`.

Tests with canned JSON fixtures: resolution, filing selection (exactly 3, correct URLs), facts mapping incl. revenue-tag fallback. Commit.

### Task 8: Global report discovery

**Files:** Create `backend/app/ingest/global_search.py`, test.

`find_annual_reports(conn, company, n=3)`: for current year Y, query `web_search` with `"{company} annual report {y} pdf"` for y in Y..Y-4 until n distinct PDFs; score candidates: `.pdf` in url (+3), "annual" and "report" in title/url (+2), year in url/title (+1), investor/ir domain hint (+1); dedupe by year; return `[{year, url, title}]`. `download_reports` uses `web.fetch_url(binary=True, ttl=0)`. Tests: mocked search results ranking, year extraction (`20\d\d` regex, pick plausible 2000..Y). Commit.

### Task 9: Facts fallback + metrics computation

**Files:** Create `backend/app/analysis/__init__.py`, `metrics.py`, `formula.py`; tests.

- `metrics.py` `compute_ratios(facts_by_year) -> [{metric, fiscal_year, value, formula, inputs:[fact_ids]}]`: net_margin, operating_margin, roe, current_ratio, debt_to_equity, revenue_growth_yoy, net_income_growth_yoy. Skip when inputs missing; never LLM. Store as facts with `source_kind="derived"`, `source_ref=json{"formula","inputs"}`.
- `formula.py` `safe_eval(expr, variables) -> float`: `ast.parse` allowing only Num/Name/BinOp(+-*/)/UnaryOp/parentheses; used later for user-defined project metrics.

Tests: ratio math incl. missing-input skip and zero-division guard; `safe_eval` rejects `__import__`, attributes, calls. Commit.

### Task 10: Embeddings + retrieval (RAG)

**Files:** Create `backend/app/rag.py`, test.

- `embed_chunks(conn, report_id, embedder)`: batch texts (64/batch), `np.asarray(vec, np.float32).tobytes()` into `chunks.embedding`.
- `search_chunks(conn, company_id, query, embedder, k=8)`: load candidate embeddings into one matrix, cosine via normalized dot; returns chunks + scores + report metadata.
- `fact_context(conn, company_id)`: all facts pivoted year×metric for prompt context.

Tests with a fake deterministic embedder (hash→vector): nearest-neighbor correctness, empty-company safety. Commit.

### Task 11: Ingestion pipeline orchestrator

**Files:** Create `backend/app/ingest/pipeline.py`, test.

`ingest_company(conn, name, source_mode, progress_cb)`: create/find company → EDGAR path (resolve→filings→download HTML→`parse_html`→chunks/tables→`company_facts`) or global path (discover→download PDFs→`parse_pdf`) → store reports/chunks/doc_tables → `embed_chunks` → table-facts fallback for global mode (scan doc_tables for rows whose first cell matches metric synonyms `revenue/total income/net profit/net income/total assets/...`, parse rightmost numeric cells; `source_kind="table"`, `source_ref={table_id,row}`) → set report status `ready`/`failed`. Runs in a thread from FastAPI BackgroundTasks; progress persisted on `reports.status` (`pending→fetching→parsing→embedding→ready|failed`) so the UI can poll. Tests: full pipeline with mocked network + fake embedder on fixtures for both modes. Commit.

### Task 12: Analysis engine

**Files:** Create `backend/app/analysis/analyze.py`, prompts in module constants; test.

`run_analysis(conn, company_id, session_key, persona_id=None)`:
1. Gather: facts pivot, derived ratios (compute+store first), top chunks for canned queries ("risk factors", "management discussion outlook", "business overview", "liquidity capital resources") each tagged `[chunk:{id}]`.
2. Prompt (json_mode): produce JSON `{executive_summary, business_overview, financial_highlights:[{statement, citations}], trends:[{metric, direction, comment, citations}], risks:[{title, summary, citations}], outlook, persona_view?}` — citations are `chunk:{id}` / `fact:{id}` strings from provided context ONLY.
3. Validate citations exist (drop unknown ids), store into `analyses` with `trace_json` = the context id map; kind=`overview`; persona system prompt prepended when persona_id.
`get_trace(conn, kind, ref_id)` resolves `chunk:`/`fact:` ids to full provenance (text excerpt / xbrl tag / table cell / formula+inputs) for the UI.
Tests: fake provider returning canned JSON → stored analysis, invalid citation dropped, token usage recorded. Commit.

### Task 13: MCP client + chat engine

**Files:** Create `backend/app/mcp_client.py`, `backend/app/chat.py`; tests.

- `mcp_client.py` (uses `mcp` SDK, async): `list_tools(server_row)` and `call_tool(server_row, name, args)`; stdio transport (`command`+`args_json`) and streamable-http (`url`). Each call opens a short-lived session (simple, stateless). Wrap with `asyncio.run` helpers so chat stays sync. Failures return error strings, never crash chat.
- `chat.py` `run_chat_turn(conn, session_id, user_text, session_key, web_enabled, mcp_enabled)`:
  system prompt = base analyst prompt + scope context (company fact pivot or project summary) + persona overlay; tools = `search_documents(query)` (rag), `get_financial_facts()`, plus `web_search(query)` if web_enabled, plus MCP tools (namespaced `mcp_{server}_{tool}`) if mcp_enabled. Tool loop max 6 iterations; every `search_documents` result carries `[chunk:{id}]` markers; final assistant message stores `citations_json` for ids referenced as `[chunk:N]`/`[fact:N]` in the reply. Persist messages; return message + citations + updated session token totals.
Tests: fake provider scripted to call a tool then answer; assert loop, persistence, citations extraction; MCP wrapper with a stub. Commit.

### Task 14: Projects + comparison

**Files:** Create `backend/app/projects.py`, test.

- CRUD helpers; `compare(conn, project_id)` → per-company fact pivots aligned on latest common fiscal years + ratio table.
- `add_custom_metric(conn, project_id, name, description, formula)` where formula references metric names (e.g. `operating_income / revenue`); validate via `formula.safe_eval` against each company's latest-year facts; store `project_metrics` with per-company results + trace (inputs used). Optional `suggest_metric(conn, project_id, prompt, session_key)` asks the LLM (json_mode) for `{name, description, formula}` using available metric names, then validates the same way.
- `run_project_analysis` (kind=`comparison`, stored in `analyses` with `project_id`): LLM narrative over the comparison table with `fact:` citations.
Tests: comparison alignment, custom metric computation + bad-formula rejection. Commit.

### Task 15: FastAPI app + API routes

**Files:** Create `backend/app/main.py`, `backend/app/api/{companies,chat,projects,personas,settings,tokens,mcp,analyses}.py`; test with `fastapi.testclient`.

Routes (JSON):
- `POST /api/companies/fetch {name, source_mode}` → starts BackgroundTasks ingestion, returns company; `GET /api/companies`, `GET /api/companies/{id}` (+reports/status), `POST /api/companies/{id}/save` toggle profile save, `DELETE /api/companies/{id}`.
- `POST /api/companies/{id}/analyze {persona_id?}` (background), `GET /api/companies/{id}/analysis?persona_id=`, `GET /api/companies/{id}/facts`, `GET /api/trace/{kind}/{id}`.
- `POST /api/chat/sessions {scope_type, scope_id, persona_id?}`, `GET /api/chat/sessions?scope=`, `GET /api/chat/sessions/{id}/messages`, `POST /api/chat/sessions/{id}/messages {text, web_enabled, mcp_enabled}`.
- Projects CRUD + `POST /api/projects/{id}/companies`, `GET /api/projects/{id}/compare`, `POST /api/projects/{id}/metrics`, `POST /api/projects/{id}/metrics/suggest`, `POST /api/projects/{id}/analyze`.
- Personas CRUD (builtin rows seeded at init: CFO, Wall Street Analyst — editable, deletable only if not builtin → actually allow delete of any; builtin flag only for re-seed guard).
- `GET/PUT /api/settings` (masked keys; PUT ignores masked placeholder `"•••"`), `GET /api/settings/providers/test` (ping current provider).
- `GET /api/tokens?session_key=` totals + per-call list; session_key generated by frontend per browser session.
- MCP servers CRUD + `GET /api/mcp/servers/{id}/tools`.
- Static: serve `frontend/dist` at `/` with SPA fallback.
Init on startup: `init_db`, seed personas/settings. One shared sqlite conn per request via dependency (`check_same_thread=False` + a lock, or per-request connections — use per-request connections, simplest correct).
Tests: happy-path per router with fake provider injected via dependency override. Commit.

### Task 16: Frontend — shell + API client

**Files:** In `frontend/src`: `api.ts` (typed fetch wrappers, session_key in localStorage), `App.tsx` (router-less view state), `components/Layout.tsx`, `styles.css` (design tokens).

Layout: CSS grid `grid-template-columns: 75fr 25fr` inside `100vh` app frame; header 56px fixed (app name, view nav: Companies · Projects · Settings, token tracker pill, provider badge); left `main` `overflow-y:auto`; right `aside` chat with own scroll; wide tables wrapped in `.scroll-x{overflow-x:auto}`. Light professional palette: near-white background `#fafbfc`, ink `#1a2233`, one accent `#2f6fed`, subtle borders `#e5e9f0`, Inter/system font stack, 13-14px base, generous whitespace, no heavy shadows. **Load `dataviz` skill before building charts.** Commit.

### Task 17: Frontend — views

**Files:** `components/CompaniesView.tsx`, `DashboardView.tsx`, `ChatPanel.tsx`, `ProjectsView.tsx`, `SettingsView.tsx`, `TokenTracker.tsx`, `TraceModal.tsx`, `PersonaPicker.tsx`.

- Companies: search input + source-mode selector (US-listed / Global) + fetch button; saved profiles grid; ingestion progress (poll company status 2s).
- Dashboard: analysis sections as cards (exec summary, highlights, trends w/ Recharts line/bar of facts by year, risks, outlook); every citation chip `[source]` opens TraceModal (calls `/api/trace/...` showing origin + excerpt/formula); facts table (years × metrics, `.scroll-x`); persona selector re-runs/loads persona analyses; "Analyze" button.
- ChatPanel: anchored to current scope (company or project); persona dropdown; toggles: Web, MCP; messages with citation chips; input; per-session token mini-counter.
- Projects: list/create; add saved companies; comparison table; custom metric form (+ "suggest with AI"); project analysis; project chat scope.
- Settings: provider select + per-provider fields (masked keys), embed provider/model, test-connection button; MCP servers table (add stdio/http), personas editor (list, edit prompt, enable, web/mcp toggles, add new).
- TokenTracker: header pill "▲ in / ▼ out" polling `/api/tokens` 5s; click → per-call breakdown popover. Commit per component group.

### Task 18: Integration, build, smoke test, README

1. `npm run build`; verify FastAPI serves SPA at `http://localhost:8000`.
2. Full pytest run green.
3. Live smoke (Ollama): fetch a real company via EDGAR (e.g. AAPL), wait for `ready`, run analysis, one chat turn with retrieval, verify token totals move, verify trace endpoint. Fix what breaks.
4. `README.md`: prerequisites, `run.ps1`/`run.sh` style start command (`.venv\Scripts\python -m uvicorn app.main:app --app-dir backend`), provider configuration, MCP examples. Final commit.

**Verification checklist (maps to the 15 requirements):** company prompt ✅T17, 3 reports fetched ✅T7/8/11, normalized parse ✅T6, persistent DB text/tables/vectors ✅T2/10, LLM analysis ✅T12, dashboard ✅T17, anchored chat + web + MCP ✅T13/17, saved profiles ✅T15/17, projects + derived metrics stored ✅T14, configurable providers ✅T4, personas w/ web+MCP ✅T13/15, traceability ✅T9/12/17, 75/20 professional layout + scrolling ✅T16, search caching ✅T5, token tracker ✅T3/17.
