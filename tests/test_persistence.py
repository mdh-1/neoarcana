"""Readings persist to SQLite, so permalinks outlive a restart."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import reading as reading_service


@pytest.fixture
def client():
    return TestClient(app)


def _draw(client, spread="celtic_cross", question="Does this survive a restart?"):
    r = client.post(
        "/readings",
        data={"spread_key": spread, "question": question},
        follow_redirects=False,
    )
    return r.headers["location"].rsplit("/", 1)[1]


def _restart():
    """Drop the connection and the in-memory cache — what a deploy does."""
    reading_service.store.reset()


def test_permalink_survives_restart(client):
    reading_id = _draw(client)
    before = reading_service.store.get(reading_id)

    _restart()

    after = reading_service.store.get(reading_id)
    assert after is not None, "reading vanished across restart"
    assert client.get(f"/readings/{reading_id}").status_code == 200


def test_rehydrated_reading_is_identical(client):
    reading_id = _draw(client)
    before = reading_service.store.get(reading_id)
    snapshot = [
        (c.card.number, c.is_reversed, c.position, c.position_name, c.display_name,
         c.picture, c.meaning)
        for c in before.cards
    ]

    _restart()
    after = reading_service.store.get(reading_id)

    assert [
        (c.card.number, c.is_reversed, c.position, c.position_name, c.display_name,
         c.picture, c.meaning)
        for c in after.cards
    ] == snapshot
    assert after.question == before.question
    assert after.entropy_source == before.entropy_source
    assert after.language_hint == before.language_hint
    assert after.created == before.created
    assert after.spread.key == before.spread.key


def test_interpretation_survives_restart(client):
    reading_id = _draw(client, spread="one_card", question="")
    client.get(f"/readings/{reading_id}/stream")  # mock provider completes it

    _restart()

    api = client.get(f"/api/v1/readings/{reading_id}").json()
    assert api["status"] == "complete"
    assert len(api["interpretation"]) > 50
    # and the finished text renders on the page rather than the pending state
    assert "Reading them now" not in client.get(f"/readings/{reading_id}").text


def test_language_hint_survives_restart(client):
    r = client.post(
        "/readings",
        data={"spread_key": "one_card", "question": ""},
        headers={"Accept-Language": "es-ES,es;q=0.9"},
        follow_redirects=False,
    )
    reading_id = r.headers["location"].rsplit("/", 1)[1]

    _restart()

    assert reading_service.store.get(reading_id).language_hint == "es-es"


def test_unknown_id_still_404s(client):
    assert reading_service.store.get("nope") is None
    assert "drifted beyond recall" in client.get("/readings/nope").text


def test_oldest_readings_are_pruned(client, monkeypatch):
    monkeypatch.setenv("READING_STORE_SIZE", "3")
    monkeypatch.setenv("READINGS_PER_HOUR", "100")
    get_settings.cache_clear()

    ids = [_draw(client, spread="one_card", question=f"q{i}") for i in range(5)]

    _restart()
    survivors = [i for i in ids if reading_service.store.get(i) is not None]
    assert survivors == ids[-3:], "should keep the three newest"


def test_reading_is_written_before_the_page_is_served(client):
    """The redirect target must be readable even by a process that never
    saw the POST — the multi-worker failure mode, in miniature."""
    reading_id = _draw(client, spread="three_card")
    _restart()
    assert reading_service.store.get(reading_id) is not None


def test_second_stream_returns_stored_text_without_regenerating(client):
    """A completed reading replays from storage. Without this, refreshing
    a finished reading would spend another LLM call and could append a
    second interpretation to the first."""
    reading_id = _draw(client, spread="one_card", question="")

    first = client.get(f"/readings/{reading_id}/stream").text
    stored = reading_service.store.get(reading_id).interpretation

    client.get(f"/readings/{reading_id}/stream")
    assert reading_service.store.get(reading_id).interpretation == stored, (
        "second stream mutated the stored interpretation"
    )
    assert stored.count("A note from the development deck") == 1


def test_completed_reading_renders_bold_not_asterisks(client):
    """The streaming path converts **bold** in reading.js; a reading loaded
    from storage must produce the same HTML, or every reload and every
    shared permalink shows literal asterisks with the drop cap on a `*`."""
    reading_id = _draw(client, spread="one_card", question="")
    client.get(f"/readings/{reading_id}/stream")   # complete it

    html = client.get(f"/readings/{reading_id}").text
    essay = html[html.index('id="essay"'):html.index("</div>", html.index('id="essay"'))]
    assert "<strong>" in essay, "bold was not rendered server-side"
    assert "**" not in essay, "literal asterisks leaked into the page"


def test_interpretation_html_escapes_before_marking_up():
    from app.main import _interpretation_html

    out = str(_interpretation_html("<script>x</script> **bold**"))
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert "<strong>bold</strong>" in out
