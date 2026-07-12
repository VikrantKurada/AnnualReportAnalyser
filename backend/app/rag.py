"""Embedding storage and brute-force cosine retrieval over SQLite blobs."""
import sqlite3

import numpy as np

BATCH = 64


def embed_chunks(conn: sqlite3.Connection, report_id: int, embedder,
                 model_name: str = "") -> int:
    rows = conn.execute(
        "SELECT id, text FROM chunks WHERE report_id = ? AND embedding IS NULL",
        (report_id,)).fetchall()
    done = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        vectors = embedder.embed([r["text"] for r in batch])
        for row, vec in zip(batch, vectors):
            blob = np.asarray(vec, dtype=np.float32).tobytes()
            conn.execute("UPDATE chunks SET embedding = ?, embed_model = ? WHERE id = ?",
                         (blob, model_name, row["id"]))
        conn.commit()
        done += len(batch)
    return done


def search_chunks(conn: sqlite3.Connection, company_id: int, query: str,
                  embedder, k: int = 8) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id, c.section, c.seq, c.text, c.page, c.embedding,"
        " r.fiscal_year, r.id AS report_id"
        " FROM chunks c JOIN reports r ON r.id = c.report_id"
        " WHERE r.company_id = ? AND c.embedding IS NOT NULL",
        (company_id,)).fetchall()
    if not rows:
        return []

    matrix = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    q = np.asarray(embedder.embed([query])[0], dtype=np.float32)

    def normalize(x, axis=None):
        norm = np.linalg.norm(x, axis=axis, keepdims=axis is not None)
        return x / np.maximum(norm, 1e-9)

    scores = normalize(matrix, axis=1) @ normalize(q)
    order = np.argsort(-scores)[:k]
    return [{
        "id": rows[i]["id"], "section": rows[i]["section"], "seq": rows[i]["seq"],
        "text": rows[i]["text"], "page": rows[i]["page"],
        "fiscal_year": rows[i]["fiscal_year"], "report_id": rows[i]["report_id"],
        "score": float(scores[i]),
    } for i in order]


def fact_context(conn: sqlite3.Connection, company_id: int) -> dict:
    """All facts pivoted metric × year, with fact ids for citations."""
    rows = conn.execute(
        "SELECT id, metric, label, fiscal_year, value, unit, source_kind"
        " FROM facts WHERE company_id = ? ORDER BY metric, fiscal_year DESC",
        (company_id,)).fetchall()
    years = sorted({r["fiscal_year"] for r in rows}, reverse=True)
    metrics: dict[str, dict] = {}
    for r in rows:
        m = metrics.setdefault(r["metric"], {
            "metric": r["metric"], "label": r["label"] or r["metric"],
            "unit": r["unit"], "source_kind": r["source_kind"],
            "values": {}, "fact_ids": {}})
        m["values"][str(r["fiscal_year"])] = r["value"]
        m["fact_ids"][str(r["fiscal_year"])] = r["id"]
    return {"years": years, "metrics": list(metrics.values())}
