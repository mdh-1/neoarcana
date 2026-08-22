import pytest

from app import main
from app.config import get_settings
from app.services import reading as reading_service


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """Every test gets a fresh database and no provider keys.

    Tests must run offline and keyless no matter what the developer's
    .env holds — a real key here would send test readings to a live LLM,
    and a real database would leak readings between tests."""
    for var in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "RANDOM_API_KEY"):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("READINGS_DB", str(tmp_path / "readings.db"))
    get_settings.cache_clear()
    reading_service.store.reset()

    # The per-IP rate limiter is module state; without a reset every test
    # file shares one bucket and whichever runs after the rate-limit test
    # sees nothing but 429s.
    main._hits.clear()

    yield

    reading_service.store.reset()
    main._hits.clear()
    get_settings.cache_clear()
