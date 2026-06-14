from lawboi.config.settings import Settings


def test_defaults(monkeypatch):
    # Make the test hermetic: clear any settings env vars that a prior test's
    # load_dotenv() may have pushed into os.environ, and disable .env loading,
    # so this exercises the in-code defaults rather than the developer's .env.
    for var in ("LLM_MODEL", "COHERE_API_KEY", "DB_POOL_MIN", "DB_POOL_MAX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    s = Settings(_env_file=None)
    assert s.db_pool_min == 1
    assert s.db_pool_max == 10
    assert s.llm_model is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    s = Settings()
    assert s.llm_model == "gpt-4o"
