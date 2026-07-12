"""App settings stored in the settings table; API keys are masked on the way out."""
import json
import sqlite3

MASK = "••••••••"

DEFAULTS: dict[str, str] = {
    "llm_provider": "ollama",
    "llm_model": "glm-4.7-flash:latest",
    "embed_provider": "ollama",
    "embed_model": "nomic-embed-text",
    "ollama_base_url": "http://localhost:11434",
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-5",
    "openai_api_key": "",
    "openai_base_url": "https://api.openai.com/v1",
    "nvidia_api_key": "",
    "nvidia_base_url": "https://integrate.api.nvidia.com/v1",
    "search_cache_ttl": "86400",
}

SECRET_KEYS = {k for k in DEFAULTS if k.endswith("_api_key")}


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return DEFAULTS.get(key, "")
    return json.loads(row["value"])


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


def all_settings(conn: sqlite3.Connection) -> dict:
    result = dict(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM settings"):
        result[row["key"]] = json.loads(row["value"])
    return result


def masked_settings(conn: sqlite3.Connection) -> dict:
    result = all_settings(conn)
    for key in SECRET_KEYS:
        if result.get(key):
            result[key] = MASK
    return result


def update_settings(conn: sqlite3.Connection, values: dict) -> None:
    for key, value in values.items():
        if key in SECRET_KEYS and value == MASK:
            continue
        set_setting(conn, key, value)
