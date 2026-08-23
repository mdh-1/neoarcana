"""The deck: validated card data and pure draw/assembly logic.

Draws are expressed as (indices, reversals) so the entropy source is
fully separated from deck logic and everything here is unit-testable.

This design fixes two legacy bugs at once: sampling -77..77 meant card 0
(The Fool) could never be reversed, and |x| collisions forced whole-spread
redraws. Sampling 0..77 without replacement plus an independent reversal
bit per card gives every card identical odds both ways.
"""

import json
from functools import lru_cache

from pydantic import BaseModel

from ..config import DATA_DIR
from .spreads import Spread

DECK_SIZE = 78

# Wands/Cups/Swords/Pentacles map to the four classical elements. Majors
# carry their own element in the data; minors and courts inherit the suit's.
SUIT_ELEMENT = {"Wands": "Fire", "Cups": "Water", "Swords": "Air", "Pentacles": "Earth"}


class ThothAttributes(BaseModel):
    """Three shapes in the wild: majors carry regalia (gemstone, weapon,
    divine name), numbered minors carry color/planet, courts carry element."""

    color: str | None = None
    thelemic_title: str | None = None
    thelemic_key: str | None = None
    gemstone: str | None = None
    magical_weapon: str | None = None
    divine_name: str | None = None
    planet: str | None = None
    element: str | None = None


class Card(BaseModel):
    """One of the 78 cards. Majors carry esoterica; minors carry a suit."""

    name: str
    number: int
    arcana: str
    description: str
    picture: str
    picture_reversed: str
    upright: str
    reversed: str
    crowley_name: str
    crowley_upright: str
    crowley_reversed: str
    numerology: int | None = None  # court cards have none
    thoth_attributes: ThothAttributes
    suit: str | None = None
    astrology: str | None = None
    element: str | None = None
    hebrew_letter: str | None = None
    qabalistic_path: str | None = None


class DrawnCard(BaseModel):
    """A card in a spread: card + orientation + server-assigned position."""

    card: Card
    is_reversed: bool
    position: int
    position_name: str
    position_description: str

    @property
    def display_name(self) -> str:
        return f"{self.card.name} (reversed)" if self.is_reversed else self.card.name

    @property
    def picture(self) -> str:
        return self.card.picture_reversed if self.is_reversed else self.card.picture

    @property
    def meaning(self) -> str:
        return self.card.reversed if self.is_reversed else self.card.upright

    @property
    def correspondences(self) -> str:
        """Golden Dawn attributions as one line, e.g. "Fire · Mars · Pe".

        Shown under the card and given to the interpreter. The scheme is
        1890s Golden Dawn, which both Waite and Crowley drew on, so nothing
        here depends on the copyrighted Thoth material.

        Three shapes, because the deck has three kinds of card: majors carry
        element/planet/Hebrew letter, courts carry element-of-element (the
        most interpretively useful of the three), and numbered minors carry
        their suit's element plus a planetary attribution.
        """
        card, th = self.card, self.card.thoth_attributes
        if card.arcana == "Major":
            parts = (card.element, card.astrology, card.hebrew_letter)
        elif th.element:  # court card, e.g. "Water of Water"
            parts = (th.element,)
        else:
            parts = (SUIT_ELEMENT.get(card.suit or ""), th.planet)
        return " · ".join(p for p in parts if p)

    @property
    def element(self) -> str:
        """Fire | Water | Air | Earth, for picking the glyph. Empty when the
        data gives no element (a court's "Water of Water" starts with one)."""
        card = self.card
        if card.arcana == "Major":
            return card.element or ""
        if card.suit:
            return SUIT_ELEMENT.get(card.suit, "")
        return ""

    @property
    def crowley_meaning(self) -> str:
        return (
            self.card.crowley_reversed if self.is_reversed else self.card.crowley_upright
        )


@lru_cache
def load_deck() -> list[Card]:
    """Load and validate the deck once. A malformed entry is a startup
    error here, not a someday-bug at render time."""
    raw = json.loads((DATA_DIR / "cards.json").read_text())
    deck = [Card.model_validate(entry) for entry in raw]
    if len(deck) != DECK_SIZE:
        raise ValueError(f"expected {DECK_SIZE} cards, got {len(deck)}")
    numbers = {c.number for c in deck}
    if numbers != set(range(DECK_SIZE)):
        raise ValueError("card numbers must be exactly 0..77 with no gaps")
    return deck


def assemble_spread(
    spread: Spread, indices: list[int], reversals: list[bool]
) -> list[DrawnCard]:
    """Map drawn indices/orientations onto a spread's positions."""
    n = spread.card_count
    if len(indices) != n or len(reversals) != n:
        raise ValueError(f"{spread.key} needs exactly {n} indices and reversals")
    if len(set(indices)) != n:
        raise ValueError("drawn indices must be unique")
    if not all(0 <= i < DECK_SIZE for i in indices):
        raise ValueError("card index out of range")

    by_number = {c.number: c for c in load_deck()}
    return [
        DrawnCard(
            card=by_number[idx],
            is_reversed=rev,
            position=pos.position,
            position_name=pos.name,
            position_description=pos.description,
        )
        for idx, rev, pos in zip(indices, reversals, spread.positions)
    ]
