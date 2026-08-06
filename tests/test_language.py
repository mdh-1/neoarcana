"""Accept-Language hint: tiebreaker for general readings and short
questions whose language the model can't detect on its own."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import reading as reading_service
from app.services.reading import _user_prompt


@pytest.fixture
def client():
    return TestClient(app)


def _create(client, headers=None, question=""):
    r = client.post(
        "/readings",
        data={"spread_key": "one_card", "question": question},
        headers=headers or {},
        follow_redirects=False,
    )
    return reading_service.store.get(r.headers["location"].rsplit("/", 1)[1])


@pytest.mark.parametrize(
    ("header", "hint"),
    [
        ("es-ES,es;q=0.9,en;q=0.8", "es-es"),
        ("fr", "fr"),
        ("de-DE;q=0.7", "de-de"),
        ("en-GB,en;q=0.9", ""),  # English is the default — no hint needed
        ("en-US", ""),
        ("*", ""),
        ("", ""),
    ],
)
def test_header_parsing(client, header, hint):
    reading = _create(client, headers={"Accept-Language": header} if header else {})
    assert reading.language_hint == hint


def test_hint_reaches_the_prompt(client):
    reading = _create(client, headers={"Accept-Language": "es-ES,es;q=0.9"})
    prompt = _user_prompt(reading)
    assert "'es-es'" in prompt
    assert "answer in that language" in prompt


def test_no_hint_keeps_prompt_clean(client):
    reading = _create(client, headers={"Accept-Language": "en-US,en;q=0.9"})
    assert "preferred language" not in _user_prompt(reading)


def test_clear_question_language_still_wins(client):
    """The hint is phrased as a tiebreaker: a question with a clear
    language takes precedence per the system prompt."""
    reading = _create(
        client,
        headers={"Accept-Language": "de-DE"},
        question="¿Debería aceptar el nuevo trabajo?",
    )
    prompt = _user_prompt(reading)
    assert "¿Debería aceptar el nuevo trabajo?" in prompt
    assert "If I asked no question, or its language is unclear" in prompt
