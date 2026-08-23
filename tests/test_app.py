"""Route smoke tests. No API keys configured in tests, so entropy is the
OS CSPRNG and the interpreter is the mock provider — full offline run."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_lists_spreads(client):
    r = client.get("/")
    assert r.status_code == 200
    for title in ("One Card", "Three Cards", "Celtic Cross"):
        assert title in r.text


def test_ask_page(client):
    r = client.get("/ask/celtic_cross")
    assert r.status_code == 200
    assert "The positions" in r.text
    assert client.get("/ask/nope").status_code == 404


def test_create_and_view_reading(client):
    r = client.post(
        "/readings",
        data={"spread_key": "three_card", "question": "Will the tests pass?"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    url = r.headers["location"]
    page = client.get(url)
    assert page.status_code == 200
    assert "Will the tests pass?" in page.text
    assert page.text.count("<figure") == 3

    # JSON API sees the same reading
    reading_id = url.rsplit("/", 1)[1]
    api = client.get(f"/api/v1/readings/{reading_id}").json()
    assert api["spread"] == "three_card"
    assert len(api["cards"]) == 3
    positions = [c["position_name"] for c in api["cards"]]
    assert positions == ["Past", "Present", "Future"]


def test_stream_completes_and_persists(client):
    r = client.post(
        "/readings", data={"spread_key": "one_card", "question": ""},
        follow_redirects=False,
    )
    reading_id = r.headers["location"].rsplit("/", 1)[1]
    stream = client.get(f"/readings/{reading_id}/stream")
    assert stream.status_code == 200
    assert "event: done" in stream.text
    # interpretation persisted onto the reading
    api = client.get(f"/api/v1/readings/{reading_id}").json()
    assert api["status"] == "complete"
    assert len(api["interpretation"]) > 50


def test_unknown_reading_404s(client):
    assert "drifted beyond recall" in client.get("/readings/nonexistent").text
    assert client.get("/api/v1/readings/nonexistent").status_code == 404


def test_rate_limit_kicks_in(client):
    from app.config import get_settings
    limit = get_settings().readings_per_hour
    last = None
    for _ in range(limit + 2):
        last = client.post(
            "/readings", data={"spread_key": "one_card", "question": ""},
            follow_redirects=False,
        )
    assert last.status_code == 429


def test_no_unrendered_jinja(client):
    for path in ("/", "/ask/one_card", "/faq"):
        assert not re.search(r"{{|}}", client.get(path).text)


@pytest.mark.parametrize("path", ["/", "/faq", "/health", "/favicon.ico", "/robots.txt", "/ask/one_card"])
def test_head_is_answered_like_get(client, path):
    """Crawlers and uptime monitors use HEAD; FastAPI's @app.get does not
    register it, so every page used to return a JSON 404 to them."""
    head, get = client.head(path), client.get(path)
    assert head.status_code == get.status_code == 200, path
    assert head.headers["content-type"] == get.headers["content-type"], path
    assert head.content == b""


def test_hint_offers_both_hover_and_tap(client):
    """Touch devices have no hover but can focus a card; the hint used to be
    hidden entirely on touch, leaving the tooltips undiscoverable there."""
    r = client.post("/readings", data={"spread_key": "celtic_cross", "question": ""},
                    follow_redirects=False)
    html = client.get(r.headers["location"]).text
    assert 'class="hint-hover">Hover<' in html
    assert 'class="hint-tap">Tap<' in html
