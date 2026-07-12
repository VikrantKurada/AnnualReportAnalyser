"""Best-effort discovery of annual-report PDFs for non-US companies via web search."""
import re
import sqlite3
from datetime import date

from .. import web

YEAR_RE = re.compile(r"(20\d\d)")


def _current_year() -> int:
    return date.today().year


def find_annual_reports(conn: sqlite3.Connection, company: str, n: int = 3) -> list[dict]:
    """Search for the company's last n annual-report PDFs, one per year."""
    current = _current_year()
    by_year: dict[int, dict] = {}

    for year in range(current, current - 5, -1):
        if len(by_year) >= n:
            break
        results = web.web_search(conn, f"{company} annual report {year} pdf",
                                 max_results=8)
        best_score, best = 0, None
        for r in results:
            score = _score(r, year)
            if score > best_score:
                best_score, best = score, r
        if best is None:
            continue
        found_year = _extract_year(best["url"], best["title"], current) or year
        if found_year not in by_year:
            by_year[found_year] = {"year": found_year, "url": best["url"],
                                   "title": best["title"]}

    return sorted(by_year.values(), key=lambda f: -f["year"])[:n]


def _score(result: dict, year: int) -> int:
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()
    text = f"{url} {title}"
    score = 0
    if url.endswith(".pdf") or ".pdf" in url:
        score += 3
    if "annual" in text and "report" in text:
        score += 2
    if str(year) in text:
        score += 1
    if any(hint in url for hint in ("investor", "/ir/", "ir.", "investors")):
        score += 1
    if any(bad in url for bad in ("wikipedia", "youtube", "facebook")):
        score -= 5
    return score


def _extract_year(url: str, title: str, current: int) -> int | None:
    for source in (url, title):
        for m in YEAR_RE.findall(source):
            y = int(m)
            if 2000 <= y <= current:
                return y
    return None


def download_report(conn: sqlite3.Connection, url: str) -> str:
    """Download a report PDF (cached forever); returns the local path."""
    return web.fetch_url(conn, url, ttl=0, binary=True)
