"""Cached web access: page fetches, binary downloads, and DDG searches.

Every fetch/search goes through web_cache (SQLite). Binary payloads live under
data/files/ and the cache stores the local path.
"""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

import httpx

try:
    from ddgs import DDGS
except ImportError:  # older package name
    from duckduckgo_search import DDGS

from . import settings as settings_mod

FILES_DIR = Path(os.environ.get("ARA_FILES_DIR", "data/files"))
USER_AGENT = "AnnualReportAnalyser/1.0 (vikrant.kurada@gmail.com)"


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True,
                        headers={"User-Agent": USER_AGENT})


def _key(kind: str, value: str) -> str:
    return f"{kind}:{hashlib.sha1(value.encode()).hexdigest()}"


def cache_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT content, fetched_at, ttl FROM web_cache WHERE key = ?",
                       (key,)).fetchone()
    if row is None:
        return None
    if row["ttl"] > 0 and row["fetched_at"] + row["ttl"] < time.time():
        return None
    return row["content"]


def cache_put(conn: sqlite3.Connection, key: str, kind: str, url: str | None,
              content: str, ttl: float = 0) -> None:
    conn.execute(
        "INSERT INTO web_cache (key, kind, url, content, fetched_at, ttl)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET"
        " content = excluded.content, fetched_at = excluded.fetched_at, ttl = excluded.ttl",
        (key, kind, url, content, time.time(), ttl),
    )
    conn.commit()


def fetch_url(conn: sqlite3.Connection, url: str, ttl: float | None = None,
              binary: bool = False) -> str:
    """Fetch a URL with caching. Text mode returns the body; binary mode
    downloads to data/files/ and returns the local path."""
    if ttl is None:
        ttl = float(settings_mod.get_setting(conn, "search_cache_ttl") or 86400)
    kind = "file" if binary else "page"
    key = _key(kind, url)
    cached = cache_get(conn, key)
    if cached is not None:
        if not binary or Path(cached).exists():
            return cached

    with _client() as client:
        r = client.get(url)
        r.raise_for_status()
        if binary:
            FILES_DIR.mkdir(parents=True, exist_ok=True)
            ext = Path(url.split("?")[0]).suffix or ".bin"
            path = FILES_DIR / f"{hashlib.sha1(url.encode()).hexdigest()}{ext}"
            path.write_bytes(r.content)
            content = str(path)
        else:
            content = r.text
    cache_put(conn, key, kind, url, content, ttl)
    return content


def web_search(conn: sqlite3.Connection, query: str, max_results: int = 8) -> list[dict]:
    ttl = float(settings_mod.get_setting(conn, "search_cache_ttl") or 86400)
    key = _key("search", f"{query}|{max_results}")
    cached = cache_get(conn, key)
    if cached is not None:
        return json.loads(cached)

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    results = [{"title": r.get("title", ""), "url": r.get("href") or r.get("url", ""),
                "snippet": r.get("body", "")} for r in raw]
    cache_put(conn, key, "search", None, json.dumps(results), ttl)
    return results
