import numpy as np

from app import db, rag


class FakeEmbedder:
    """Deterministic 4-dim embeddings keyed by known words."""
    VOCAB = {"revenue": 0, "risk": 1, "cash": 2, "widgets": 3}

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.zeros(4)
            for word, i in self.VOCAB.items():
                if word in t.lower():
                    v[i] = 1.0
            if not v.any():
                v[:] = 0.25
            out.append(v.tolist())
        return out


def setup_company(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar"})
    rid = db.insert(conn, "reports", {"company_id": cid, "fiscal_year": 2025,
                                      "status": "ready"})
    for seq, (section, text) in enumerate([
        ("MD&A", "Revenue grew due to strong widgets demand"),
        ("Risk Factors", "Key risk is competition"),
        ("Liquidity", "Cash position is strong"),
    ]):
        db.insert(conn, "chunks", {"report_id": rid, "section": section,
                                   "seq": seq, "text": text})
    return conn, cid, rid


def test_embed_chunks_stores_vectors(tmp_path):
    conn, cid, rid = setup_company(tmp_path)
    n = rag.embed_chunks(conn, rid, FakeEmbedder(), model_name="fake")
    assert n == 3
    rows = db.query(conn, "SELECT embedding, embed_model FROM chunks WHERE report_id=?", (rid,))
    assert all(r["embedding"] is not None for r in rows)
    assert rows[0]["embed_model"] == "fake"
    vec = np.frombuffer(rows[0]["embedding"], dtype=np.float32)
    assert vec.shape == (4,)


def test_search_chunks_ranks_by_similarity(tmp_path):
    conn, cid, rid = setup_company(tmp_path)
    rag.embed_chunks(conn, rid, FakeEmbedder(), model_name="fake")
    hits = rag.search_chunks(conn, cid, "what is the risk", FakeEmbedder(), k=2)
    assert len(hits) == 2
    assert hits[0]["section"] == "Risk Factors"
    assert hits[0]["score"] >= hits[1]["score"]
    assert hits[0]["fiscal_year"] == 2025


def test_search_chunks_empty_company(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    cid = db.insert(conn, "companies", {"name": "Empty", "source_mode": "edgar"})
    assert rag.search_chunks(conn, cid, "anything", FakeEmbedder()) == []


def test_fact_context_pivots(tmp_path):
    conn, cid, rid = setup_company(tmp_path)
    for fy, val in [(2025, 100.0), (2024, 80.0)]:
        db.insert(conn, "facts", {"company_id": cid, "fiscal_year": fy,
                                  "metric": "revenue", "value": val,
                                  "source_kind": "xbrl"})
    pivot = rag.fact_context(conn, cid)
    assert pivot["years"] == [2025, 2024]
    row = next(r for r in pivot["metrics"] if r["metric"] == "revenue")
    assert row["values"] == {"2025": 100.0, "2024": 80.0}
    assert row["fact_ids"]["2025"] > 0
