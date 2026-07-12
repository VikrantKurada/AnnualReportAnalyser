"""OpenAI-compatible chat/embeddings; also used for NVIDIA NIM endpoints."""
import json

import httpx

from .base import ChatResult

TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, model: str,
                 client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def chat(self, messages, tools=None, json_mode=False) -> ChatResult:
        body = {"model": self.model, "messages": _to_openai(messages)}
        if tools:
            body["tools"] = tools
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = self.client.post(f"{self.base_url}/chat/completions",
                             json=body, headers=self._headers())
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append({"id": tc["id"], "name": tc["function"]["name"],
                               "arguments": args})
        usage = data.get("usage") or {}
        return ChatResult(
            content=msg.get("content"),
            tool_calls=tool_calls,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = self.client.post(f"{self.base_url}/embeddings",
                             json={"model": self.model, "input": texts},
                             headers=self._headers())
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]


def _to_openai(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        msg = {"role": m["role"], "content": m.get("content")}
        if m.get("tool_calls"):
            msg["tool_calls"] = [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                for tc in m["tool_calls"]
            ]
        if m.get("tool_call_id"):
            msg["tool_call_id"] = m["tool_call_id"]
        out.append(msg)
    return out
