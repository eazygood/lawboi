import os
from typing import Optional

from lawboi.ports.llm import LLMProvider
from lawboi.adapters.llm.registry import REGISTRY, find_spec
from lawboi.domain.errors import UnsupportedModelError, NoModelConfiguredError


def available_models() -> list[str]:
    return [s.name for s in REGISTRY if os.getenv(s.api_key_env)]


def resolve_model(model: Optional[str]) -> str:
    model = model or os.getenv("LLM_MODEL")
    if model:
        spec = find_spec(model)
        if spec is None:
            raise UnsupportedModelError(model)
        if not os.getenv(spec.api_key_env):
            raise NoModelConfiguredError(
                f"Model '{model}' requires {spec.api_key_env} to be set")
        return model
    for spec in sorted(REGISTRY, key=lambda s: s.priority):
        if os.getenv(spec.api_key_env):
            return spec.name
    raise NoModelConfiguredError(
        "No LLM API key configured. Set one of: "
        + ", ".join(sorted({s.api_key_env for s in REGISTRY})))


def build_llm(model: Optional[str] = None) -> LLMProvider:
    name = resolve_model(model)
    spec = find_spec(name)
    assert spec is not None  # resolve_model only returns names present in REGISTRY
    api_key = os.getenv(spec.api_key_env)
    assert api_key is not None  # resolve_model already checked this env var is set
    return spec.build(name, api_key)
