"""Parse SEC-style HTML filings into sections and tables.

Handles inline-XBRL noise: ix:header (hidden metadata) is dropped, other ix:
wrappers are unwrapped so the visible numbers survive.
"""
import re

from bs4 import BeautifulSoup, Tag

from .common import ParsedDoc

ITEM_RE = re.compile(r"^item\s+\d+[a-z]?\b", re.IGNORECASE)
HEADING_TAGS = {"h1", "h2", "h3", "h4"}
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "table"}


def parse(html: str) -> ParsedDoc:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(lambda t: t.name and t.name.startswith("ix:")):
        if tag.parent is None:  # already removed with an ancestor
            continue
        if tag.name in ("ix:header", "ix:hidden"):
            tag.decompose()
        else:
            tag.unwrap()

    doc = ParsedDoc()
    root = soup.body or soup
    current = {"title": "Document", "text_parts": [], "page": None}
    sections = []

    def flush():
        text = "\n\n".join(current["text_parts"]).strip()
        if text:
            sections.append({"title": current["title"], "text": text, "page": None})

    last_heading = "Document"
    for block in _iter_blocks(root):
        if block.name == "table":
            rows = _table_rows(block)
            if rows:
                doc.tables.append({"caption": last_heading, "rows": rows,
                                   "page": None, "section": last_heading})
            continue
        text = _clean(block.get_text(" ", strip=True))
        if not text:
            continue
        if _is_heading(block, text):
            flush()
            last_heading = text
            current = {"title": text, "text_parts": [], "page": None}
        else:
            current["text_parts"].append(text)
    flush()

    doc.sections = sections
    return doc


def _iter_blocks(root: Tag):
    """Yield leaf block elements in document order (divs only when they have
    no block children, so nested wrappers don't duplicate text)."""
    for el in root.find_all(BLOCK_TAGS):
        if el.name == "div" and el.find(BLOCK_TAGS - {"div"}) is not None:
            continue
        if el.name != "table" and el.find_parent("table") is not None:
            continue
        if el.name == "div" and el.find("div") is not None:
            continue
        yield el


def _is_heading(block: Tag, text: str) -> bool:
    if block.name in HEADING_TAGS:
        return True
    if len(text) > 150:
        return False
    if ITEM_RE.match(text):
        return True
    bold = block.find(["b", "strong"])
    if bold and _clean(bold.get_text(" ", strip=True)) == text and len(text) < 100:
        return True
    return False


def _table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True))
                 for td in tr.find_all(["td", "th"])]
        if any(c for c in cells):
            rows.append(cells)
    return rows


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
