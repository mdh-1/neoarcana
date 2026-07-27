"""Spread definitions — the single source of truth for positions.

Positions are assigned server-side at draw time and never round-trip
through the LLM (the legacy app let the model overwrite them, which
desynced labels from descriptions whenever the model paraphrased)."""

from pydantic import BaseModel


class Position(BaseModel):
    position: int
    name: str
    description: str


class Spread(BaseModel):
    key: str
    title: str
    tagline: str
    positions: list[Position]

    @property
    def card_count(self) -> int:
        return len(self.positions)


SPREADS: dict[str, Spread] = {
    s.key: s
    for s in [
        Spread(
            key="one_card",
            title="One Card",
            tagline="A single insight — thirty seconds",
            positions=[
                Position(
                    position=1,
                    name="Situation",
                    description=(
                        "This card represents the current situation or the main focus "
                        "of the reading. It can provide insight into your current state "
                        "of mind or the primary issue at hand."
                    ),
                )
            ],
        ),
        Spread(
            key="three_card",
            title="Three Cards",
            tagline="Past, present, future — two minutes",
            positions=[
                Position(
                    position=1,
                    name="Past",
                    description=(
                        "The past influences that have led to the current situation — "
                        "what has shaped your current circumstances."
                    ),
                ),
                Position(
                    position=2,
                    name="Present",
                    description=(
                        "The current situation or state of mind. It reflects what is "
                        "happening in life at this moment."
                    ),
                ),
                Position(
                    position=3,
                    name="Future",
                    description=(
                        "The potential outcome based on the current path — what to "
                        "expect if the current course is continued."
                    ),
                ),
            ],
        ),
        Spread(
            key="celtic_cross",
            title="Celtic Cross",
            tagline="The full ten-card examination — five minutes",
            positions=[
                Position(
                    position=1,
                    name="The Present",
                    description=(
                        "What is happening at the present time; your current state of "
                        "mind and how you may be perceiving the situation."
                    ),
                ),
                Position(
                    position=2,
                    name="The Challenge",
                    description=(
                        "The immediate challenge or problem — the one thing that, if "
                        "resolved, would make life a lot easier. Even a 'positive' card "
                        "here still represents a challenge."
                    ),
                ),
                Position(
                    position=3,
                    name="The Past",
                    description=(
                        "The events that led up to the present situation, and perhaps "
                        "an indication of how the challenge came about."
                    ),
                ),
                Position(
                    position=4,
                    name="The Future",
                    description=(
                        "What is likely to occur within the next few weeks or months — "
                        "not the final outcome, simply the next step on the journey."
                    ),
                ),
                Position(
                    position=5,
                    name="Above",
                    description=(
                        "Your goal, aspiration or best outcome with regard to the "
                        "situation — what you are consciously working towards."
                    ),
                ),
                Position(
                    position=6,
                    name="Below",
                    description=(
                        "The subconscious realm: the underlying feelings and trends "
                        "driving the situation, which may carry a surprise message."
                    ),
                ),
                Position(
                    position=7,
                    name="Advice",
                    description=(
                        "A recommendation for what approach can be taken to address "
                        "the current challenges, in light of everything else drawn."
                    ),
                ),
                Position(
                    position=8,
                    name="External Influences",
                    description=(
                        "The people, energies or events beyond your control that will "
                        "affect the outcome of the question."
                    ),
                ),
                Position(
                    position=9,
                    name="Hopes and Fears",
                    description=(
                        "Hopes and fears are closely intertwined: that which we hope "
                        "for may also be that which we fear, and so may fail to happen."
                    ),
                ),
                Position(
                    position=10,
                    name="Outcome",
                    description=(
                        "Where the situation is headed if the current course is "
                        "continued — and it remains within your free will to change it."
                    ),
                ),
            ],
        ),
    ]
}

# URL slugs used by the legacy frontend, kept as aliases.
SLUG_ALIASES = {
    "one-card": "one_card",
    "three-card": "three_card",
    "celtic-cross": "celtic_cross",
}


def resolve_spread(key: str) -> Spread | None:
    return SPREADS.get(SLUG_ALIASES.get(key, key))
