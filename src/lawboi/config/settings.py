from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cohere_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    db_pool_min: int = 1
    db_pool_max: int = 10
    cors_origins: list[str] = ["http://localhost:3000"]
    answer_rate_limit: str = "10/minute"
    search_rate_limit: str = "30/minute"
