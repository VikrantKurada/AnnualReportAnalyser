"""Provider-agnostic chat/embedding interface.

Messages use OpenAI-style dicts: {"role", "content", "tool_calls"?, "tool_call_id"?}.
Tools use OpenAI function schema: {"type": "function", "function": {...}}.
Adapters translate to each vendor's wire format.
"""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[dict] = field(default_factory=list)  # {"id","name","arguments":dict}
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             json_mode: bool = False) -> ChatResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
