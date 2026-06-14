from dataclasses import dataclass
from typing import Callable, Optional

from lawboi.ports.llm import LLMProvider
from lawboi.adapters.llm.gemini import GeminiAdapter
from lawboi.adapters.llm.openai import OpenAIAdapter
from lawboi.adapters.llm.anthropic import AnthropicAdapter


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    api_key_env: str
    build: Callable[[str, str], LLMProvider]
    priority: int


REGISTRY: tuple[ModelSpec, ...] = (
    ModelSpec("gemini-2.0-flash", "google", "GEMINI_API_KEY", GeminiAdapter, 1),
    ModelSpec("gemini-1.5-pro", "google", "GEMINI_API_KEY", GeminiAdapter, 1),
    ModelSpec("gpt-4o", "openai", "OPENAI_API_KEY", OpenAIAdapter, 2),
    ModelSpec("gpt-4o-mini", "openai", "OPENAI_API_KEY", OpenAIAdapter, 2),
    ModelSpec("claude-sonnet-4-5", "anthropic", "ANTHROPIC_API_KEY", AnthropicAdapter, 3),
)


def find_spec(name: str) -> Optional[ModelSpec]:
    return next((s for s in REGISTRY if s.name == name), None)
