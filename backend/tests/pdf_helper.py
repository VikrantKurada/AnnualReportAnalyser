"""Builds a minimal valid PDF (text only) for parser tests, no extra deps."""


def build_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    n_pages = len(pages)
    font_obj_num = 3 + 2 * n_pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())

    for i, lines in enumerate(pages):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_num} 0 R "
            f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>".encode()
        )
        parts = ["BT /F1 12 Tf 72 720 Td 14 TL"]
        for j, line in enumerate(lines):
            safe = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            if j > 0:
                parts.append("T*")
            parts.append(f"({safe}) Tj")
        parts.append("ET")
        stream = " ".join(parts).encode()
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for num, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)
