from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"


class Settings(BaseSettings):
    """All keys are optional: with none set, the app runs with local
    entropy and the mock interpreter so development needs no secrets."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    random_api_key: str | None = None
    mistral_api_key: str | None = None
    deepseek_api_key: str | None = None
    grok_api_key: str | None = None

    # Provider priority, first available key wins; falls through on errors.
    llm_providers: str = "deepseek,grok,mistral"

    readings_per_hour: int = 10  # per client IP
    reading_store_size: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
