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
    # the fallback must be disclosed; wording is free to change
    assert "falls back" in faq


def test_reading_page_reflects_actual_source_not_configuration(client):
    """A key being configured is not the same as random.org having
    answered. The kicker reads the reading's recorded source."""
    reading_id = _draw(client)
    reading = reading_service.store.get(reading_id)

    reading.entropy_source = "random.org"  # as if the service had answered
    assert "shuffled by atmospheric noise" in client.get(f"/readings/{reading_id}").text

    reading.entropy_source = "local"       # as if it had fallen back
    assert "shuffled by cryptographic randomness" in client.get(f"/readings/{reading_id}").text


def test_meta_description_follows_the_configuration(client, monkeypatch):
    """The description Google shows is a claim like any other: it must not
    promise atmospheric noise when the shuffle is local."""
    html = client.get("/").text
    desc = html[html.index('name="description"'):]
    desc = desc[:desc.index(">")]
    assert "cryptographic randomness" in desc
    assert "atmospheric" not in desc


def test_readings_are_kept_out_of_the_index(client):
    """A reading carries the querent's question, so it must not be indexed."""
    r = client.post("/readings", data={"spread_key": "one_card", "question": "private"},
                    follow_redirects=False)
    html = client.get(r.headers["location"]).text
    assert 'name="robots" content="noindex, nofollow"' in html

    robots = client.get("/robots.txt").text
    assert "Disallow: /readings/" in robots
    assert "Disallow: /api/" in robots


def test_public_pages_are_indexable_and_canonical(client):
    for path in ("/", "/faq", "/ask/three_card"):
        html = client.get(path).text
        assert "noindex" not in html, path
        assert 'rel="canonical"' in html, path


def test_favicon_served_from_root_for_crawlers(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.content[:4] == b"\x00\x00\x01\x00", "not a real .ico container"


def test_sitemap_lists_the_public_pages_only(client):
    xml = client.get("/sitemap.xml").text
    assert "/faq" in xml and "/ask/celtic_cross" in xml
    assert "/readings/" not in xml


def test_prompt_asks_for_a_view_but_guards_against_invented_patterns():
    """A side-by-side experiment (Sept 2026) showed the old prompt produced
    the same platitude on every model, and a first revision asking for
    patterns made three of four models invent an elemental pattern that was
    not in the cards. Both halves of the fix live in the prompt text."""
    from app.services.reading import SYSTEM_PROMPT

    # asks for a view
    assert "Say which way the spread leans" in SYSTEM_PROMPT
    assert "Do not describe it back to them" in SYSTEM_PROMPT
    # guards against confabulation
    assert "Name a pattern only when it is actually there" in SYSTEM_PROMPT
    assert "must be true of every card in it" in SYSTEM_PROMPT
    # the phrase that triggered the hallucination is gone
    assert "shift from one element to the next" not in SYSTEM_PROMPT

