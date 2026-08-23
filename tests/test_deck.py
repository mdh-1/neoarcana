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


def test_recorded_image_dimensions_match_the_files():
    """The width/height in cards.json reserve layout space in the browser.
    If the images are ever re-processed and the data is not regenerated,
    every card would be laid out to the wrong box, so check them against
    the files rather than trusting the record."""
    import struct

    from app.config import BASE_DIR

    def jpeg_size(path):
        with open(path, "rb") as f:
            assert f.read(2) == b"\xff\xd8", path
            while True:
                b = f.read(1)
                while b and b != b"\xff":
                    b = f.read(1)
                marker = f.read(1)
                while marker == b"\xff":
                    marker = f.read(1)
                if marker[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    f.read(3)
                    h, w = struct.unpack(">HH", f.read(4))
                    return w, h
                (length,) = struct.unpack(">H", f.read(2))
                f.seek(length - 2, 1)

    static = BASE_DIR / "static" / "tarot-images"
    for card in load_deck():
        recorded = (card.picture_width, card.picture_height)
        assert jpeg_size(static / card.picture) == recorded, card.name
        # the reversed face is the same box rotated; a mismatch would make
        # reversed cards shift on load while upright ones did not
        assert jpeg_size(static / card.picture_reversed) == recorded, card.name


def test_every_card_declares_a_plausible_size():
    for card in load_deck():
        assert 300 < card.picture_width < 500, card.name
        assert card.picture_height == 640, card.name
