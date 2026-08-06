import pytest

from app import main


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The per-IP rate limiter is module state; without a reset, every test
    file shares one bucket and whichever file runs after the rate-limit
    test sees nothing but 429s."""
    main._hits.clear()
    yield
    main._hits.clear()
