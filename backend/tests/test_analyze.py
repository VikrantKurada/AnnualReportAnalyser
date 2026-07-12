import json

from app import db, rag
from app.analysis import analyze
from app.providers.base import ChatResult

from .test_rag import FakeEmbedder


class FakeLLM:
    """Mimics TrackedLLM.chat(messages, tools=None, json_mode=False, context='')."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, tools=None, json_mode=False, context=""):
        self.calls.append({"messages": messages, "tools": tools,
                           "json_mode": json_mode, "context": context})
        return self.responses.pop(0)


def seed_company(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    cid = db.insert(conn, "companies", {"name": "Acme", "source_mode": "edgar",
                                        "status": "ready"})
    rid = db.insert(conn, "reports", {"company_id": cid, "fiscal_year": 2025,
                                      "status": "ready", "source_url": "https://x/10k.htm"})
    chunk_id = db.insert(conn, "chunks", {"report_id": rid, "section": "Risk Factors",
                                          "seq": 0, "text": "Competition risk is high"})
    rag.embed_chunks(conn, rid, FakeEmbedder(), model_name="fake")
    fact_id = db.insert(conn, "facts", {"company_id": cid, "fiscal_year": 2025,
                                        "metric": "revenue", "label": "Revenue",
                                        "value": 1000.0, "source_kind": "xbrl",
                                        "source_ref": json.dumps({"tag": "Revenues", "accn": "a1"})})
    return conn, cid, chunk_id, fact_id


def analysis_json(chunk_id, fact_id, extra_citation="chunk:99999"):
    return json.dumps({
        "executive_summary": "Acme grew revenue.",
        "business_overview": "Widgets.",
        "financial_highlights": [
            {"statement": "Revenue hit 1000", "citations": [f"fact:{fact_id}"]}],
        "trends": [{"metric": "revenue", "direction": "up", "comment": "growth",
                    "citations": [f"fact:{fact_id}", extra_citation]}],
        "risks": [{"title": "Competition", "summary": "Rivals",
                   "citations": [f"chunk:{chunk_id}"]}],
        "outlook": "Positive.",
    })


def test_run_analysis_stores_validated_result(tmp_path):
    conn, cid, chunk_id, fact_id = seed_company(tmp_path)
    llm = FakeLLM([ChatResult(content=analysis_json(chunk_id, fact_id))])
    aid = analyze.run_analysis(conn, cid, "sess", llm=llm, embedder=FakeEmbedder())

    row = db.query(conn, "SELECT * FROM analyses WHERE id=?", (aid,))[0]
    content = json.loads(row["content_json"])
    assert content["executive_summary"] == "Acme grew revenue."
    # bogus citation dropped, real ones kept
    assert content["trends"][0]["citations"] == [f"fact:{fact_id}"]
    assert content["risks"][0]["citations"] == [f"chunk:{chunk_id}"]
    assert row["kind"] == "overview"
    assert llm.calls[0]["json_mode"] is True
    # prompt contains context markers
    prompt_text = json.dumps(llm.calls[0]["messages"])
    assert f"chunk:{chunk_id}" in prompt_text
    assert f"fact:{fact_id}" in prompt_text


def test_run_analysis_with_persona(tmp_path):
    conn, cid, chunk_id, fact_id = seed_company(tmp_path)
    pid = db.insert(conn, "personas", {"name": "CFO", "system_prompt": "You are the CFO."})
    llm = FakeLLM([ChatResult(content=analysis_json(chunk_id, fact_id))])
    aid = analyze.run_analysis(conn, cid, "sess", persona_id=pid, llm=llm,
                               embedder=FakeEmbedder())
    row = db.query(conn, "SELECT * FROM analyses WHERE id=?", (aid,))[0]
    assert row["persona_id"] == pid
    assert "You are the CFO." in llm.calls[0]["messages"][0]["content"]


def test_run_analysis_tolerates_fenced_json(tmp_path):
    conn, cid, chunk_id, fact_id = seed_company(tmp_path)
    fenced = "```json\n" + analysis_json(chunk_id, fact_id) + "\n```"
    llm = FakeLLM([ChatResult(content=fenced)])
    aid = analyze.run_analysis(conn, cid, "sess", llm=llm, embedder=FakeEmbedder())
    assert aid > 0


def test_get_trace_chunk_fact_derived(tmp_path):
    conn, cid, chunk_id, fact_id = seed_company(tmp_path)
    derived_id = db.insert(conn, "facts", {
        "company_id": cid, "fiscal_year": 2025, "metric": "net_margin",
        "value": 0.2, "source_kind": "derived",
        "source_ref": json.dumps({"formula": "net_income / revenue",
                                  "inputs": [fact_id]})})

    t = analyze.get_trace(conn, "chunk", chunk_id)
    assert t["kind"] == "chunk"
    assert t["section"] == "Risk Factors"
    assert t["source_url"] == "https://x/10k.htm"

    t = analyze.get_trace(conn, "fact", fact_id)
    assert t["source_kind"] == "xbrl"
    assert t["detail"]["tag"] == "Revenues"

    t = analyze.get_trace(conn, "fact", derived_id)
    assert t["source_kind"] == "derived"
    assert t["detail"]["formula"] == "net_income / revenue"
    assert t["inputs"][0]["metric"] == "revenue"
