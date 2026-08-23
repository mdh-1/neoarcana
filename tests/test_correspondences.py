"""Golden Dawn correspondences: shown to the reader, given to the model."""

import pytest
from fastapi.testclient import TestClient

from app.domain.deck import SUIT_ELEMENT, assemble_spread, load_deck
from app.domain.spreads import SPREADS
from app.main import app
from app.services import reading as reading_service
from app.services.reading import SYSTEM_PROMPT, _user_prompt


@pytest.fixture
def client():
    return TestClient(app)


def _card(number, reversed_=False):
    return assemble_spread(SPREADS["one_card"], [number], [reversed_])[0]


def test_the_three_card_shapes():
    assert _card(15).correspondences == "Earth · Capricorn · Ayin"   # major
    assert _card(68).correspondences == "Fire · Saturn in Leo"       # numbered minor
    assert _card(47).correspondences == "Fire of Earth"              # court


def test_every_card_has_correspondences_and_an_element():
    """A blank line under one card in seventy-eight would look like a bug."""
    for n in range(len(load_deck())):
        c = _card(n)
        assert c.correspondences, f"{c.display_name} has no correspondences"
        assert c.element in SUIT_ELEMENT.values(), f"{c.display_name}: {c.element!r}"


def test_reversal_does_not_change_correspondences():
    """Orientation changes the meaning, not the card's attributions."""
    assert _card(15).correspondences == _card(15, True).correspondences


def test_prompt_carries_them_and_forbids_naming_them():
    r = reading_service.store.get(
        _draw(TestClient(app), "three_card")
    )
    prompt = _user_prompt(r)
    for c in r.cards:
        assert f"(correspondences: {c.correspondences})" in prompt
    assert "Never name them" in SYSTEM_PROMPT
    assert "not a lesson in symbolism" in SYSTEM_PROMPT


def _draw(client, spread):
    resp = client.post(
        "/readings", data={"spread_key": spread, "question": ""}, follow_redirects=False
    )
    return resp.headers["location"].rsplit("/", 1)[1]


@pytest.mark.parametrize("spread", ["one_card", "three_card", "celtic_cross"])
def test_rendered_on_every_spread(client, spread):
    html = client.get(f"/readings/{_draw(client, spread)}").text
    r = reading_service.store.get(_draw(client, spread))
    assert 'class="corr"' in html
    assert "svg class=\"el\"" in html or "<svg" in html


def test_glyph_is_svg_not_unicode(client):
    """U+1F700 renders as tofu on most Windows and Android."""
    html = client.get(f"/readings/{_draw(client, 'celtic_cross')}").text
    assert "🜂" not in html and "🜁" not in html and "🜃" not in html and "🜄" not in html
    assert 'class="el"' in html


def test_celtic_cross_shows_them_in_tooltip_and_index(client):
    html = client.get(f"/readings/{_draw(client, 'celtic_cross')}").text
    # once per tooltip (8 cards + 2 in the crossed centre) and once per index row
    assert html.count('class="corr"') >= 20
