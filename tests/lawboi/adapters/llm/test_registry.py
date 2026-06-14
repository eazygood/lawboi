import pytest
from lawboi.adapters.llm.registry import REGISTRY, ModelSpec, find_spec
from lawboi.adapters.llm.factory import available_models, resolve_model
from lawboi.domain.errors import UnsupportedModelError, NoModelConfiguredError


def test_registry_entries_well_formed():
    assert REGISTRY
    for spec in REGISTRY:
        assert isinstance(spec, ModelSpec)
        assert spec.name and spec.provider and spec.api_key_env
        assert callable(spec.build)


def test_available_models_derives_from_env(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    models = available_models()
    assert "gpt-4o" in models
    assert "gemini-2.0-flash" not in models


def test_resolve_picks_priority_default(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert resolve_model(None) == "gpt-4o"


def test_resolve_rejects_unknown(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(UnsupportedModelError):
        resolve_model("gpt-5")


def test_resolve_raises_when_nothing_configured(monkeypatch):
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(NoModelConfiguredError):
        resolve_model(None)


def test_find_spec():
    assert find_spec("gpt-4o").provider == "openai"
