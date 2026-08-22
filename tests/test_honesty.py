"""The site's claims about the shuffle must match what actually happened.

With no random.org key every draw is local CSPRNG, and the copy must say
so; with a key, the copy may speak of atmospheric noise — and each reading
still names its own source, since the key can be configured and the
service still fail."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import reading as reading_service


@pytest.fixture
def client():
    return TestClient(app)


def _draw(client):
    r = client.post("/readings", data={"spread_key": "one_card", "question": ""},
                    follow_redirects=False)
    return r.headers["location"].rsplit("/", 1)[1]


# --- keyless (conftest default): nothing may mention random.org ---------

def test_keyless_footer_is_honest(client):
    html = client.get("/").text
    assert "cryptographic randomness" in html
    assert "random.org" not in html
    assert "atmospheric" not in html


def test_keyless_faq_is_honest(client):
    html = client.get("/faq").text
    assert "cryptographic random number generator" in html
    assert "random.org" not in html


def test_keyless_reading_names_its_source(client):
    reading_id = _draw(client)
    assert reading_service.store.get(reading_id).entropy_source == "local"
    html = client.get(f"/readings/{reading_id}").text
    assert "shuffled by cryptographic randomness" in html
    assert "atmospheric" not in html


# --- key configured: the claim is allowed, and still per-reading --------

@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("RANDOM_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_configured_footer_and_faq_claim_random_org(client, with_key):
    # index and FAQ render without drawing, so no network call happens
    assert "atmospheric noise" in client.get("/").text
    assert "random.org" in client.get("/").text
    faq = client.get("/faq").text
    assert "atmospheric noise" in faq and "random.org" in faq
    assert "every reading states which one it got" in faq


def test_reading_page_reflects_actual_source_not_configuration(client):
    """A key being configured is not the same as random.org having
    answered. The kicker reads the reading's recorded source."""
    reading_id = _draw(client)
    reading = reading_service.store.get(reading_id)

    reading.entropy_source = "random.org"  # as if the service had answered
    assert "shuffled by atmospheric noise" in client.get(f"/readings/{reading_id}").text

    reading.entropy_source = "local"       # as if it had fallen back
    assert "shuffled by cryptographic randomness" in client.get(f"/readings/{reading_id}").text
