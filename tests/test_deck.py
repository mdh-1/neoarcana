"""Deck and spread logic — the pure core, no I/O."""

import pytest

from app.domain.deck import DECK_SIZE, assemble_spread, load_deck
from app.domain.spreads import SPREADS, resolve_spread


def test_deck_loads_and_validates():
    deck = load_deck()
    assert len(deck) == DECK_SIZE
    assert {c.number for c in deck} == set(range(DECK_SIZE))


def test_every_card_has_both_orientations():
    for c in load_deck():
        assert c.upright and c.reversed
        assert c.picture.endswith(".jpg")
        assert c.picture_reversed.endswith(".jpg")


def test_majors_and_minors_carry_their_fields():
    deck = load_deck()
    majors = [c for c in deck if c.arcana == "Major"]
    minors = [c for c in deck if c.arcana == "Minor"]
    assert len(majors) == 22 and len(minors) == 56
    assert all(c.hebrew_letter for c in majors)
    assert all(c.suit in {"Cups", "Pentacles", "Swords", "Wands"} for c in minors)


def test_assemble_celtic_cross():
    spread = SPREADS["celtic_cross"]
    indices = list(range(10))
    reversals = [i % 2 == 0 for i in range(10)]
    drawn = assemble_spread(spread, indices, reversals)
    assert len(drawn) == 10
    assert drawn[0].position_name == "The Present"
    assert drawn[-1].position_name == "Outcome"
    # The Fool (index 0) CAN be reversed now — the legacy -77..77 bug is dead.
    assert drawn[0].card.number == 0 and drawn[0].is_reversed
    assert "(reversed)" in drawn[0].display_name
    assert drawn[0].picture == drawn[0].card.picture_reversed
    assert drawn[0].meaning == drawn[0].card.reversed


def test_assemble_rejects_bad_input():
    spread = SPREADS["one_card"]
    with pytest.raises(ValueError):
        assemble_spread(spread, [1, 2], [False])  # wrong count
    with pytest.raises(ValueError):
        assemble_spread(spread, [99], [False])  # out of range
    with pytest.raises(ValueError):
        assemble_spread(SPREADS["three_card"], [5, 5, 6], [False] * 3)  # dupe


def test_spread_slug_aliases():
    assert resolve_spread("celtic-cross") is SPREADS["celtic_cross"]
    assert resolve_spread("celtic_cross") is SPREADS["celtic_cross"]
    assert resolve_spread("bogus") is None
