from app.services import reading as reading_service
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
    assert "positions" in r.text
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


def _reading_html(client, spread):
    r = client.post("/readings", data={"spread_key": spread, "question": ""},
                    follow_redirects=False)
    return client.get(r.headers["location"]).text


def test_cross_cards_are_buttons_that_open_a_panel(client):
    """On the Celtic Cross a card has room for its name and little else, so
    each opens a panel. The trigger is a real button that says whether its
    panel is open: the focusable figure it replaced announced nothing to a
    screen reader. Ten cards, nine triggers (I and II share the centre)."""
    html = _reading_html(client, "celtic_cross")
    assert html.count('class="card-btn" aria-expanded="false"') == 9
    assert html.count('class="tip" id="tip-') == 9
    assert html.count('class="tip-close" aria-label="Close"') == 9
    assert "tabindex=\"0\"" not in html


def test_plates_carry_no_panel(client):
    """One and three card spreads print the meaning under the card. A panel
    there repeated it, and covered the question or the next caption."""
    for spread in ("one_card", "three_card"):
        html = _reading_html(client, spread)
        assert 'class="tip"' not in html, spread
        assert "card-btn" not in html, spread
        assert "Select a card" not in html, spread


def test_reading_page_has_a_heading_and_a_way_to_the_reading(client):
    """The question is the page's heading, and a link under it leads to the
    essay: on a phone the cards fill several screens before it."""
    html = _reading_html(client, "celtic_cross")
    assert '<h1 class="question' in html
    assert 'id="reading-status" href="#essay"' in html
    assert "<main" in html


def test_reference_follows_the_reading(client):
    """The card-by-card index is reference. It stood between the cards and
    the essay; it now comes after, closed."""
    html = _reading_html(client, "celtic_cross")
    assert html.index('id="essay"') < html.index('class="cc-index"')
    assert '<details class="cc-index">' in html


def test_unknown_page_gets_the_themed_error_not_json(client):
    r = client.get("/nowhere")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "not in the deck" in r.text
    # programs still get JSON
    api = client.get("/api/v1/readings/nonexistent")
    assert api.status_code == 404 and "application/json" in api.headers["content-type"]


def test_question_is_stored_as_one_line(client):
    """The form is a textarea now, and a newline would break the quoted line
    the question occupies in the prompt."""
    r = client.post("/readings", data={"spread_key": "one_card",
                                       "question": "first line\nsecond   line"},
                    follow_redirects=False)
    rid = r.headers["location"].rsplit("/", 1)[1]
    assert reading_service.store.get(rid).question == "first line second line"
