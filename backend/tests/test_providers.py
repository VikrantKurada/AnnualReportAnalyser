import json

import httpx

from app import db
from app.providers.anthropic import AnthropicProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers import registry


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- Ollama ----------

def test_ollama_chat_parses_content_and_tokens():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "hello"},
            "prompt_eval_count": 12, "eval_count": 7,
        })

    p = OllamaProvider(base_url="http://x:11434", model="glm", client=mock_client(handler))
    res = p.chat([{"role": "user", "content": "hi"}])
    assert captured["url"] == "http://x:11434/api/chat"
    assert captured["body"]["stream"] is False
    assert res.content == "hello"
    assert res.input_tokens == 12 and res.output_tokens == 7
    assert res.tool_calls == []


def test_ollama_chat_tool_calls_and_json_mode():
    def handler(request):
        body = json.loads(request.content)
        assert body["format"] == "json"
        assert body["tools"][0]["function"]["name"] == "search"
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": "search", "arguments": {"q": "revenue"}}}]},
            "prompt_eval_count": 1, "eval_count": 2,
        })

    p = OllamaProvider(base_url="http://x:11434", model="glm", client=mock_client(handler))
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    res = p.chat([{"role": "user", "content": "hi"}], tools=tools, json_mode=True)
    assert res.tool_calls == [{"id": "call_0", "name": "search", "arguments": {"q": "revenue"}}]


def test_ollama_embed():
    def handler(request):
        body = json.loads(request.content)
        assert body["input"] == ["a", "b"]
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    p = OllamaProvider(base_url="http://x:11434", model="nomic", client=mock_client(handler))
    assert p.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


# ---------- OpenAI-compatible (OpenAI + NVIDIA) ----------

def test_openai_chat_json_mode_and_tokens():
    def handler(request):
        assert request.headers["authorization"] == "Bearer sk-k"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "{\"a\":1}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 9},
        })

    p = OpenAICompatProvider(base_url="https://api.openai.com/v1", api_key="sk-k",
                             model="gpt-x", client=mock_client(handler))
    res = p.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert res.content == "{\"a\":1}"
    assert res.input_tokens == 5 and res.output_tokens == 9


def test_openai_tool_calls_parsed():
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "search", "arguments": "{\"q\": \"x\"}"}}]}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    p = OpenAICompatProvider(base_url="https://x/v1", api_key="k", model="m",
                             client=mock_client(handler))
    res = p.chat([{"role": "user", "content": "hi"}])
    assert res.tool_calls == [{"id": "c1", "name": "search", "arguments": {"q": "x"}}]


def test_openai_embed():
    def handler(request):
        return httpx.Response(200, json={
            "data": [{"embedding": [0.1, 0.2], "index": 0}],
            "usage": {"prompt_tokens": 2, "total_tokens": 2},
        })

    p = OpenAICompatProvider(base_url="https://x/v1", api_key="k", model="m",
                             client=mock_client(handler))
    assert p.embed(["a"]) == [[0.1, 0.2]]


# ---------- Anthropic ----------

def test_anthropic_translation_and_tokens():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["headers"] = request.headers
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "hi there"},
                        {"type": "tool_use", "id": "tu1", "name": "search", "input": {"q": "x"}}],
            "usage": {"input_tokens": 3, "output_tokens": 4},
        })

    p = AnthropicProvider(api_key="ak", model="claude-sonnet-5", client=mock_client(handler))
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "t0", "name": "search", "arguments": {"q": "y"}}]},
        {"role": "tool", "tool_call_id": "t0", "content": "result text"},
    ]
    tools = [{"type": "function", "function": {"name": "search", "description": "d",
                                               "parameters": {"type": "object"}}}]
    res = p.chat(messages, tools=tools)

    body = captured["body"]
    assert captured["headers"]["x-api-key"] == "ak"
    assert body["system"] == "be brief"
    assert body["tools"][0]["input_schema"] == {"type": "object"}
    # assistant tool call became a tool_use block; tool msg became tool_result
    assert body["messages"][1]["content"][0]["type"] == "tool_use"
    assert body["messages"][2]["content"][0]["type"] == "tool_result"
    assert body["messages"][2]["role"] == "user"
    assert res.content == "hi there"
    assert res.tool_calls == [{"id": "tu1", "name": "search", "arguments": {"q": "x"}}]
    assert res.input_tokens == 3 and res.output_tokens == 4


# ---------- Registry ----------

class FakeProvider:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def chat(self, messages, tools=None, json_mode=False):
        from app.providers.base import ChatResult
        return ChatResult(content="ok", tool_calls=[], input_tokens=11,
                          output_tokens=22, raw={})

    def embed(self, texts):
        return [[0.0] for _ in texts]


def test_registry_records_tokens(tmp_path, monkeypatch):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    monkeypatch.setitem(registry.CHAT_FACTORIES, "ollama", lambda conn: (FakeProvider(), "fake-model"))
    llm = registry.get_llm(conn, session_key="s1")
    res = llm.chat([{"role": "user", "content": "hi"}], context="chat")
    assert res.content == "ok"
    from app import tokens
    totals = tokens.session_totals(conn, "s1")
    assert totals == {"input_tokens": 11, "output_tokens": 22, "calls": 1}
