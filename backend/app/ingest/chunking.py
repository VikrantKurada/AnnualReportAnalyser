"""Split sections into overlapping chunks sized for embedding and retrieval."""


def chunk_sections(sections: list[dict], target: int = 1800,
                   overlap: int = 200) -> list[dict]:
    chunks = []
    seq = 0
    for section in sections:
        for text in _split_text(section["text"], target, overlap):
            chunks.append({"section": section["title"], "seq": seq,
                           "text": text, "page": section.get("page")})
            seq += 1
    return chunks


def _split_text(text: str, target: int, overlap: int) -> list[str]:
    if len(text) <= target:
        return [text] if text.strip() else []

    paragraphs = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > int(target * 1.5):  # hard-split runaway paragraphs
            cut = para.rfind(" ", target - 200, target)
            cut = cut if cut > 0 else target
            paragraphs.append(para[:cut])
            para = para[cut:].strip()
        paragraphs.append(para)

    out: list[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) > target and buf:
            out.append(buf)
            buf = buf[-overlap:] + "\n\n" + para if overlap else para
        else:
            buf = candidate
    if buf.strip():
        out.append(buf)
    return out
