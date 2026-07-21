from lawboi.config.settings import Settings


def test_defaults(monkeypatch):
    # Make the test hermetic: clear any settings env vars that a prior test's
    # load_dotenv() may have pushed into os.environ, and disable .env loading,
    # so this exercises the in-code defaults rather than the developer's .env.
    for var in ("LLM_MODEL", "COHERE_API_KEY", "DB_POOL_MIN", "DB_POOL_MAX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.db_pool_min == 5
    assert s.db_pool_max == 50
    assert s.llm_model is None
    assert s.cache_version_suffix == ""


def test_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    s = Settings()  # type: ignore[call-arg]
    assert s.llm_model == "gpt-4o"
