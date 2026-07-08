from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cohere_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    db_pool_min: int = 5
    db_pool_max: int = 50
    cors_origins: list[str] = ["http://localhost:3000"]
    answer_rate_limit: str = "10/minute"
    search_rate_limit: str = "30/minute"
    trusted_proxies: list[str] = []   # e.g. ["10.0.0.0/8"] for internal load balancer


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
