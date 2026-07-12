from pathlib import Path

from app.ingest import chunking, parse_html, parse_pdf

from .pdf_helper import build_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_html_sections():
    doc = parse_html.parse((FIXTURES / "mini_10k.html").read_text(encoding="utf-8"))
    titles = [s["title"] for s in doc.sections]
    assert "Item 1. Business" in titles
    assert "Item 1A. Risk Factors" in titles
    assert any("Management" in t for t in titles)

    business = next(s for s in doc.sections if s["title"] == "Item 1. Business")
    assert "widgets worldwide" in business["text"]
    assert "three segments" in business["text"]  # ix: tags unwrapped, not dropped
    assert "hidden xbrl metadata" not in " ".join(s["text"] for s in doc.sections)
    assert "console.log" not in " ".join(s["text"] for s in doc.sections)

    risks = next(s for s in doc.sections if s["title"] == "Item 1A. Risk Factors")
    assert "competition" in risks["text"]


def test_parse_html_tables():
    doc = parse_html.parse((FIXTURES / "mini_10k.html").read_text(encoding="utf-8"))
    assert len(doc.tables) == 1
    t = doc.tables[0]
    assert t["rows"][0] == ["Metric", "2025", "2024"]
    assert t["rows"][1] == ["Revenue", "1,200", "1,071"]
    assert "Management" in t["caption"]
    # table content must not leak into section text
    assert "1,200" not in " ".join(s["text"] for s in doc.sections)


def test_parse_pdf_sections_and_pages(tmp_path):
    pdf_bytes = build_pdf([
        ["RISK FACTORS",
         "Widget demand may decline substantially.",
         "Competition is intense in all markets."],
        ["LIQUIDITY AND CAPITAL RESOURCES",
         "Cash position remains strong at year end."],
    ])
    path = tmp_path / "mini.pdf"
    path.write_bytes(pdf_bytes)

    doc = parse_pdf.parse(str(path))
    titles = [s["title"] for s in doc.sections]
    assert "RISK FACTORS" in titles
    assert "LIQUIDITY AND CAPITAL RESOURCES" in titles
    risk = next(s for s in doc.sections if s["title"] == "RISK FACTORS")
    assert "demand may decline" in risk["text"]
    assert risk["page"] == 1
    liq = next(s for s in doc.sections if s["title"] == "LIQUIDITY AND CAPITAL RESOURCES")
    assert liq["page"] == 2


def test_chunking_splits_and_overlaps():
    para = "Lorem ipsum dolor sit amet. " * 20  # ~560 chars
    sections = [{"title": "MD&A", "text": "\n\n".join([para] * 8), "page": 3}]
    chunks = chunking.chunk_sections(sections, target=1000, overlap=150)
    assert len(chunks) >= 3
    assert all(c["section"] == "MD&A" for c in chunks)
    assert [c["seq"] for c in chunks] == list(range(len(chunks)))
    assert all(len(c["text"]) <= 1600 for c in chunks)
    assert all(c["page"] == 3 for c in chunks)
    # consecutive chunks share overlapping text
    tail = chunks[0]["text"][-50:]
    assert tail in chunks[1]["text"]


def test_chunking_hard_splits_giant_paragraph():
    sections = [{"title": "S", "text": "x" * 5000, "page": None}]
    chunks = chunking.chunk_sections(sections, target=1000, overlap=100)
    assert len(chunks) >= 4
    assert all(len(c["text"]) <= 1600 for c in chunks)
