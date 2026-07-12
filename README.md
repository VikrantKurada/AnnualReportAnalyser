# Annual Report Analyser

A local web app that fetches a company's last three annual reports, parses them into
structured text / tables / financial facts, stores everything in a persistent SQLite
database (including vector embeddings), runs LLM analysis, and presents the results on
a dashboard with an anchored chat panel.

## Features

- **Two ingestion modes** per company: **US-listed** (SEC EDGAR 10-K filings + official
  XBRL financial facts) or **Global best-effort** (web search for annual-report PDFs).
- **Persistent storage** across sessions in one SQLite file (`data/app.db`): section
  text, extracted tables, financial facts, embeddings, analyses, chats, projects.
- **Traceability everywhere**: every number and claim carries a citation chip — click
  it to see the XBRL tag, table cell, formula + inputs, or document excerpt it came
  from. Derived ratios are computed in Python, never by the LLM.
- **Chat anchored in the data** with tools: document retrieval, financial facts,
  optional cached **web search**, and optional **MCP servers** (stdio or HTTP).
- **Configurable LLM providers**: Ollama (default), Claude API, OpenAI, NVIDIA —
  switchable in Settings, including a separate embeddings provider.
- **Personas** (CFO and Wall Street Analyst built in, fully editable) applied to
  analyses and chats, each with its own web/MCP permissions.
- **Projects**: compare saved company profiles side by side, define custom comparison
  metrics (validated formulas over stored facts, optionally suggested by the LLM), and
  persist the results.
- **Token tracker** in the header showing live session input/output token usage with a
  per-call breakdown.
- **Web-search caching** with a configurable TTL; filings and PDFs are cached forever.

## Prerequisites

- Python 3.12+ (developed on 3.14) and Node 20+ (only needed to rebuild the frontend)
- [Ollama](https://ollama.com) running locally for the default configuration, with:
  `ollama pull glm-4.7-flash` (chat) and `ollama pull nomic-embed-text` (embeddings) —
  or configure another provider in Settings.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install; npm run build; cd ..
```

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
```

Open http://localhost:8000. All data lands in `data/` (safe to delete for a reset).

For frontend development with hot reload: `cd frontend; npm run dev` (proxies `/api`
to port 8000).

## Tests

```powershell
cd backend; ..\.venv\Scripts\python -m pytest
```

## Configuration notes

- **Providers**: Settings → LLM provider. API keys are stored in the local database
  and masked in the UI. NVIDIA uses the OpenAI-compatible endpoint
  (`https://integrate.api.nvidia.com/v1`).
- **MCP servers**: Settings → MCP servers. stdio example: command `npx`, args
  `-y @modelcontextprotocol/server-everything`. HTTP servers take a streamable-HTTP
  URL. Enable the "MCP tools" toggle in chat to expose their tools to the model.
- **SEC fair-access**: EDGAR requests send a contact User-Agent as SEC requires;
  edit `USER_AGENT` in `backend/app/web.py` to use your own contact address.

## Architecture

```
backend/app
├── db.py, schema.sql      SQLite layer (text, tables, facts, vectors as blobs)
├── settings.py, tokens.py Config + token accounting
├── providers/             Ollama / OpenAI / NVIDIA / Anthropic adapters + registry
├── web.py                 Cached fetches & DuckDuckGo search
├── ingest/                EDGAR client, global PDF discovery, HTML/PDF parsers,
│                          chunking, pipeline orchestrator, table-facts fallback
├── rag.py                 Embeddings + cosine retrieval
├── analysis/              Ratios w/ traces, safe formula eval, LLM analysis engine
├── chat.py, mcp_client.py Tool-loop chat + MCP integration
├── projects.py            Comparisons + custom metrics
└── main.py, api/          FastAPI app + routes, serves frontend/dist
frontend/src               React + Vite + TS: 75/20 dashboard-chat layout
```
