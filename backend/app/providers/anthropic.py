import httpx

from .base import ChatResult

TIMEOUT = httpx.Timeout(300.0, connect=10.0)
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096,
                 client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def chat(self, messages, tools=None, json_mode=False) -> ChatResult:
        system, anthro_messages = _to_anthropic(messages)
        if json_mode:
            system = (system + "\n\n" if system else "") + "Respond with valid JSON only."
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": anthro_messages}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {"name": t["function"]["name"],
                 "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters", {"type": "object"})}
                for t in tools
            ]
        r = self.client.post(API_URL, json=body, headers={
            "x-api-key": self.api_key, "anthropic-version": API_VERSION})
        r.raise_for_status()
        data = r.json()
        text_parts, tool_calls = [], []
        for block in data.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append({"id": block["id"], "name": block["name"],
                                   "arguments": block.get("input") or {}})
        usage = data.get("usage") or {}
        return ChatResult(
            content="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            raw=data,
        )

    def embed(self, texts):
        raise NotImplementedError("Anthropic has no embeddings API; configure a different embed provider")


def _to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts, out = [], []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m.get("content") or "")
        elif role == "tool":
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                 "content": m.get("content") or ""}]})
        elif role == "assistant" and m.get("tool_calls"):
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                blocks.append({"type": "tool_use", "id": tc["id"],
                               "name": tc["name"], "input": tc["arguments"]})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return "\n\n".join(p for p in system_parts if p), out
