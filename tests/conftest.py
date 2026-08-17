import pytest

from app import main
from app.config import get_settings


@pytest.fixture(autouse=True)
def keyless_settings(monkeypatch):
    """Tests must run offline and keyless no matter what the developer's
    .env holds — a real key here would send test readings to a live LLM.
    Empty env vars outrank the .env file and are falsy to the provider
    filter, so the mock interpreter and local entropy always run."""
    for var in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "RANDOM_API_KEY"):
        monkeypatch.setenv(var, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The per-IP rate limiter is module state; without a reset, every test
    file shares one bucket and whichever file runs after the rate-limit
    test sees nothing but 429s."""
    main._hits.clear()
    yield
    main._hits.clear()
