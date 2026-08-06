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
    gemini_api_key: str | None = None

    # Provider priority, first available key wins; falls through on errors.
    llm_providers: str = "deepseek,gemini,mistral"

    # Model IDs are config, not code: when a vendor retires a slug
    # (deepseek-chat and grok-3-mini both died in 2026), the fix is a
    # .env edit, not a deploy.
    deepseek_model: str = "deepseek-v4-flash"
    gemini_model: str = "gemini-2.5-flash-lite"
    mistral_model: str = "mistral-small-latest"

    readings_per_hour: int = 10  # per client IP
    reading_store_size: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
