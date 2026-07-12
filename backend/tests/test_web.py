import httpx

from app import db, web


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def test_cache_roundtrip_and_ttl(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    now = [1000.0]
    monkeypatch.setattr(web.time, "time", lambda: now[0])

    web.cache_put(conn, "k1", "search", None, "payload", ttl=100)
    assert web.cache_get(conn, "k1") == "payload"
    now[0] = 1099.0
    assert web.cache_get(conn, "k1") == "payload"
    now[0] = 1101.0
    assert web.cache_get(conn, "k1") is None  # expired

    web.cache_put(conn, "k2", "file", None, "forever", ttl=0)
    now[0] = 10**9
    assert web.cache_get(conn, "k2") == "forever"


def test_fetch_url_text_cached(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text="<html>hi</html>")

    monkeypatch.setattr(web, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    a = web.fetch_url(conn, "https://example.com/page", ttl=3600)
    b = web.fetch_url(conn, "https://example.com/page", ttl=3600)
    assert a == b == "<html>hi</html>"
    assert calls["n"] == 1  # second hit served from cache


def test_fetch_url_binary_saves_file(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    monkeypatch.setattr(web, "FILES_DIR", tmp_path / "files")

    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.4 fake")

    monkeypatch.setattr(web, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    path = web.fetch_url(conn, "https://example.com/r.pdf", ttl=0, binary=True)
    assert path.endswith(".pdf")
    from pathlib import Path
    assert Path(path).read_bytes() == b"%PDF-1.4 fake"
    # cached: second call returns same path without refetch
    assert web.fetch_url(conn, "https://example.com/r.pdf", ttl=0, binary=True) == path


def test_web_search_cached(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)
    calls = {"n": 0}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, query, max_results=8):
            calls["n"] += 1
            return [{"title": "T", "href": "https://x.com/a.pdf", "body": "snippet"}]

    monkeypatch.setattr(web, "DDGS", FakeDDGS)
    r1 = web.web_search(conn, "acme annual report", max_results=5)
    r2 = web.web_search(conn, "acme annual report", max_results=5)
    assert r1 == r2 == [{"title": "T", "url": "https://x.com/a.pdf", "snippet": "snippet"}]
    assert calls["n"] == 1
