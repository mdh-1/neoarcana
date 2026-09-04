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
    # Gemini leads since DeepSeek's Aug 2026 move to peak/off-peak pricing.
    llm_providers: str = "gemini,mistral,deepseek"

    # Model IDs are config, not code: when a vendor retires a slug
    # (deepseek-chat and grok-3-mini both died in 2026), the fix is a
    # .env edit, not a deploy.
    deepseek_model: str = "deepseek-v4-flash"
    # 3.8-flash over 3.5-flash-lite after a side-by-side on the same cards and
    # question (Sept 2026): the only tier that leaned, saw the real pattern
    # and did not invent a false one. Also faster than 3.5-flash, oddly.
    gemini_model: str = "gemini-3.8-flash"
    mistral_model: str = "mistral-small-latest"

    # Canonical origin, used for <link rel=canonical>, og:url and the
    # sitemap. www is canonical here (the apex 301s to it), matching the
    # Caddy config.
    site_url: str = "https://www.neoarcana.net"

    readings_per_hour: int = 10  # per client IP

    # Readings persist here so permalinks survive restarts and deploys.
    # Under systemd this points at the StateDirectory; see deploy/.
    readings_db: Path = DATA_DIR / "readings.db"
    reading_store_size: int = 5000  # oldest rows pruned beyond this


@lru_cache
def get_settings() -> Settings:
    return Settings()
