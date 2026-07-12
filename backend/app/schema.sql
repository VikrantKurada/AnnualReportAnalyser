CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ticker TEXT,
    cik TEXT,
    source_mode TEXT NOT NULL DEFAULT 'edgar',
    exchange TEXT,
    profile_json TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    error TEXT,
    saved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    fiscal_year INTEGER,
    form TEXT,
    source_url TEXT,
    local_path TEXT,
    format TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    filed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    section TEXT,
    seq INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    page INTEGER,
    embedding BLOB,
    embed_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_report ON chunks(report_id);

CREATE TABLE IF NOT EXISTS doc_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    section TEXT,
    page INTEGER,
    caption TEXT,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    report_id INTEGER,
    fiscal_year INTEGER NOT NULL,
    metric TEXT NOT NULL,
    label TEXT,
    value REAL,
    unit TEXT,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    UNIQUE(company_id, fiscal_year, metric, source_kind)
);
CREATE INDEX IF NOT EXISTS idx_facts_company ON facts(company_id);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    persona_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'overview',
    content_json TEXT NOT NULL,
    trace_json TEXT,
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS personas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    web_enabled INTEGER NOT NULL DEFAULT 1,
    mcp_enabled INTEGER NOT NULL DEFAULT 1,
    builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_companies (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    UNIQUE(project_id, company_id)
);

CREATE TABLE IF NOT EXISTS project_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    formula TEXT NOT NULL,
    results_json TEXT,
    trace_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL,
    scope_id INTEGER,
    persona_id INTEGER,
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    tool_calls_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS web_cache (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    url TEXT,
    content TEXT,
    fetched_at REAL NOT NULL,
    ttl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    context TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_session ON token_usage(session_key);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'stdio',
    command TEXT,
    url TEXT,
    args_json TEXT,
    enabled INTEGER NOT NULL DEFAULT 1
);
