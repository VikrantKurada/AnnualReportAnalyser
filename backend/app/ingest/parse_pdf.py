"""Parse annual-report PDFs into sections (heading heuristics) and tables."""
import re

import pdfplumber

from .common import ParsedDoc

ITEM_RE = re.compile(r"^item\s+\d+[a-z]?\b", re.IGNORECASE)


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not (3 < len(line) < 90):
        return False
    if ITEM_RE.match(line):
        return True
    alpha = [c for c in line if c.isalpha()]
    return len(alpha) >= 4 and line.upper() == line and not line[0].isdigit()


def parse(path: str) -> ParsedDoc:
    doc = ParsedDoc()
    sections = []
    current = None

    with pdfplumber.open(path) as pdf:
        for pageno, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if _is_heading(stripped):
                    if current and current["text_parts"]:
                        sections.append(_finish(current))
                    current = {"title": stripped, "text_parts": [], "page": pageno}
                else:
                    if current is None:
                        current = {"title": f"Page {pageno}", "text_parts": [],
                                   "page": pageno}
                    current["text_parts"].append(stripped)

            for rows in page.extract_tables():
                cleaned = [[(c or "").strip() for c in row] for row in rows if any(row)]
                if cleaned:
                    doc.tables.append({
                        "caption": current["title"] if current else f"Page {pageno}",
                        "rows": cleaned, "page": pageno,
                        "section": current["title"] if current else None,
                    })

    if current and current["text_parts"]:
        sections.append(_finish(current))
    doc.sections = sections
    return doc


def _finish(current: dict) -> dict:
    return {"title": current["title"], "text": "\n".join(current["text_parts"]),
            "page": current["page"]}
