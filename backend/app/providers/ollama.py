import httpx

from .base import ChatResult

TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class OllamaProvider:
    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def chat(self, messages, tools=None, json_mode=False) -> ChatResult:
        body = {"model": self.model, "messages": _to_ollama(messages), "stream": False}
        if tools:
            body["tools"] = tools
        if json_mode:
            body["format"] = "json"
        r = self.client.post(f"{self.base_url}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message", {})
        tool_calls = [
            {"id": f"call_{i}", "name": tc["function"]["name"],
             "arguments": tc["function"].get("arguments") or {}}
            for i, tc in enumerate(msg.get("tool_calls") or [])
        ]
        return ChatResult(
            content=msg.get("content") or None,
            tool_calls=tool_calls,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            raw=data,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = self.client.post(f"{self.base_url}/api/embed",
                             json={"model": self.model, "input": texts})
        r.raise_for_status()
        return r.json()["embeddings"]


def _to_ollama(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        msg = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            msg["tool_calls"] = [
                {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in m["tool_calls"]
            ]
        out.append(msg)
    return out
