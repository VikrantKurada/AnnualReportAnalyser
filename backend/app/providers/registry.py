"""Builds providers from settings; wraps chat so every call records token usage."""
import sqlite3

from .. import settings as settings_mod
from .. import tokens
from .anthropic import AnthropicProvider
from .base import ChatResult, LLMProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider


def _ollama_chat(conn):
    s = settings_mod.all_settings(conn)
    return OllamaProvider(s["ollama_base_url"], s["llm_model"]), s["llm_model"]


def _openai_chat(conn):
    s = settings_mod.all_settings(conn)
    return OpenAICompatProvider(s["openai_base_url"], s["openai_api_key"], s["llm_model"]), s["llm_model"]


def _nvidia_chat(conn):
    s = settings_mod.all_settings(conn)
    return OpenAICompatProvider(s["nvidia_base_url"], s["nvidia_api_key"], s["llm_model"]), s["llm_model"]


def _anthropic_chat(conn):
    s = settings_mod.all_settings(conn)
    return AnthropicProvider(s["anthropic_api_key"], s["anthropic_model"]), s["anthropic_model"]


CHAT_FACTORIES = {
    "ollama": _ollama_chat,
    "openai": _openai_chat,
    "nvidia": _nvidia_chat,
    "anthropic": _anthropic_chat,
}


def _embed_factory(conn, provider_name: str):
    s = settings_mod.all_settings(conn)
    model = s["embed_model"]
    if provider_name == "ollama":
        return OllamaProvider(s["ollama_base_url"], model)
    if provider_name == "openai":
        return OpenAICompatProvider(s["openai_base_url"], s["openai_api_key"], model)
    if provider_name == "nvidia":
        return OpenAICompatProvider(s["nvidia_base_url"], s["nvidia_api_key"], model)
    raise ValueError(f"provider {provider_name!r} cannot embed")


class TrackedLLM:
    """Delegates to a provider and records token usage per call."""

    def __init__(self, provider: LLMProvider, conn: sqlite3.Connection,
                 session_key: str, provider_name: str, model: str):
        self.provider = provider
        self.conn = conn
        self.session_key = session_key
        self.provider_name = provider_name
        self.model = model

    def chat(self, messages, tools=None, json_mode=False, context="") -> ChatResult:
        res = self.provider.chat(messages, tools=tools, json_mode=json_mode)
        tokens.record_usage(self.conn, self.session_key, self.provider_name,
                            self.model, res.input_tokens, res.output_tokens, context)
        return res


def get_llm(conn: sqlite3.Connection, session_key: str) -> TrackedLLM:
    name = settings_mod.get_setting(conn, "llm_provider")
    factory = CHAT_FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"unknown llm_provider {name!r}")
    provider, model = factory(conn)
    return TrackedLLM(provider, conn, session_key, name, model)


def get_embedder(conn: sqlite3.Connection):
    name = settings_mod.get_setting(conn, "embed_provider")
    return _embed_factory(conn, name)
