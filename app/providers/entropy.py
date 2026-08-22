"""Entropy sources for shuffling.

random.org (true atmospheric randomness) when a key is configured and the
service cooperates; otherwise the OS CSPRNG. A reading records which source
shuffled it so the UI can be honest about it — and quota exhaustion
degrades gracefully instead of turning into a 500.
"""

import logging
import secrets

import httpx

from ..domain.deck import DECK_SIZE

RANDOM_ORG_URL = "https://api.random.org/json-rpc/4/invoke"


class EntropyResult:
    __slots__ = ("indices", "reversals", "source")

    def __init__(self, indices: list[int], reversals: list[bool], source: str):
        self.indices = indices
        self.reversals = reversals
        self.source = source


def _local_draw(n: int) -> EntropyResult:
    rng = secrets.SystemRandom()
    return EntropyResult(
        indices=rng.sample(range(DECK_SIZE), n),
        reversals=[bool(secrets.randbits(1)) for _ in range(n)],
        source="local",
    )


async def draw_entropy(n: int, random_api_key: str | None) -> EntropyResult:
    """n unique card indices plus n independent reversal bits.

    One generateIntegerSequences call fetches both sequences (the legacy
    -77..77 scheme needed redraw loops and could never reverse The Fool).
    """
    if not random_api_key:
        return _local_draw(n)

    payload = {
        "jsonrpc": "2.0",
        "method": "generateIntegerSequences",
        "params": {
            "apiKey": random_api_key,
            "n": 2,
            "length": [n, n],
            "min": [0, 0],
            "max": [DECK_SIZE - 1, 1],
            "replacement": [False, True],
        },
        "id": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(RANDOM_ORG_URL, json=payload)
            resp.raise_for_status()
            body = resp.json()
        if "error" in body:
            raise RuntimeError(body["error"].get("message", "random.org error"))
        indices, bits = body["result"]["random"]["data"]
        return EntropyResult(
            indices=indices,
            reversals=[bool(b) for b in bits],
            source="random.org",
        )
    except Exception as exc:
        # Any failure — quota, network, schema — falls back to the OS CSPRNG.
        # The reading records the source, so the fallback is honest; log it
        # so that a quota exhausted at 3am is visible in the morning.
        logging.getLogger(__name__).warning("random.org unavailable (%r); using local entropy", exc)
        return _local_draw(n)
