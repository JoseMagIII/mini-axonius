from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://admin:acme-admin@localhost:5544/assets"
    reader_password: str = "acme-reader"
    data_dir: Path = ROOT / "data"

    anthropic_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5"
    agent_max_steps: int = 8
    query_row_limit: int = 200

    nvd_api_key: str | None = None
    nvd_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
