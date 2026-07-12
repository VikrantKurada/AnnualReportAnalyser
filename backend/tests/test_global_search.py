from app import db
from app.ingest import global_search


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def test_find_annual_reports_ranks_and_dedupes(tmp_path, monkeypatch):
    conn = make_conn(tmp_path)

    def fake_search(conn, query, max_results=8):
        year = next((w for w in query.split() if w.isdigit()), "2025")
        return [
            {"title": f"Acme Annual Report {year}",
             "url": f"https://acme.com/investors/annual-report-{year}.pdf",
             "snippet": "Annual report"},
            {"title": "Acme wikipedia", "url": "https://en.wikipedia.org/wiki/Acme",
             "snippet": "encyclopedia"},
            {"title": f"Random blog {year}", "url": f"https://blog.example.com/{year}",
             "snippet": "blog"},
        ]

    monkeypatch.setattr(global_search.web, "web_search", fake_search)
    monkeypatch.setattr(global_search, "_current_year", lambda: 2026)

    found = global_search.find_annual_reports(conn, "Acme", n=3)
    assert len(found) == 3
    years = [f["year"] for f in found]
    assert years == sorted(years, reverse=True)
    assert all(f["url"].endswith(".pdf") for f in found)
    assert len({f["year"] for f in found}) == 3  # deduped by year


def test_extract_year():
    assert global_search._extract_year("https://x.com/annual-2024.pdf", "report", 2026) == 2024
    assert global_search._extract_year("https://x.com/a.pdf", "Annual Report 2023", 2026) == 2023
    assert global_search._extract_year("https://x.com/a.pdf", "no year here", 2026) is None
    # implausible years rejected
    assert global_search._extract_year("https://x.com/a-9999.pdf", "", 2026) is None
