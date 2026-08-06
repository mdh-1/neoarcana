"""LLM providers behind one streaming interface.

All three commercial backends speak the OpenAI chat-completions dialect,
so one thin httpx client covers them — no per-vendor SDKs. Interpretations
are streamed as markdown-ish prose; positions and card names are server
truth and never parsed back out of model output (the legacy JSON
round-trip crashed whenever the model paraphrased a card name).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from ..config import Settings


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    key_attr: str  # attribute on Settings holding the API key
    model_attr: str  # attribute on Settings holding the model ID
    temperature: float = 1.1


PROVIDER_SPECS = {
    "deepseek": ProviderSpec(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        key_attr="deepseek_api_key",
        model_attr="deepseek_model",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_attr="gemini_api_key",
        model_attr="gemini_model",
    ),
    "mistral": ProviderSpec(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        key_attr="mistral_api_key",
        model_attr="mistral_model",
    ),
}


async def _stream_openai_compat(
    spec: ProviderSpec, settings: Settings, system: str, user: str
) -> AsyncIterator[str]:
    payload = {
        "model": getattr(settings, spec.model_attr),
        "temperature": spec.temperature,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    api_key = getattr(settings, spec.key_attr)
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        async with client.stream(
            "POST",
            f"{spec.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if chunk := delta.get("content"):
                    yield chunk


_MOCK_TEXT = (
    "**A note from the development deck.** No LLM API key is configured, so "
    "this interpretation is a stand-in streamed by the mock provider.\n\n"
    "Each card above still shows its traditional meaning — the draw itself "
    "is real and used true randomness where available.\n\n"
    "**The thread.** Add a DeepSeek, Gemini or Mistral key to `.env` and this "
    "space will hold a genuine reading, streamed card by card."
)


async def _stream_mock(system: str, user: str) -> AsyncIterator[str]:
    for word in _MOCK_TEXT.split(" "):
        yield word + " "
        await asyncio.sleep(0.02)


def available_providers(settings: Settings) -> list[str]:
    """Configured priority order, filtered to providers with keys."""
    names = [n.strip() for n in settings.llm_providers.split(",") if n.strip()]
    return [
        n
        for n in names
        if n in PROVIDER_SPECS and getattr(settings, PROVIDER_SPECS[n].key_attr)
    ]


async def stream_interpretation(
    settings: Settings, system: str, user: str
) -> AsyncIterator[str]:
    """Try providers in priority order; fall through on failure.

    The fallback chain lives server-side now — the legacy app hardcoded it
    in the browser, where a failed primary meant up to four LLM calls."""
    last_error: Exception | None = None
    for name in available_providers(settings):
        spec = PROVIDER_SPECS[name]
        try:
            got_content = False
            async for chunk in _stream_openai_compat(spec, settings, system, user):
                got_content = True
                yield chunk
            if got_content:
                return
        except Exception as exc:  # try the next provider
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    # No keys at all: mock keeps development fully offline-friendly.
    async for chunk in _stream_mock(system, user):
        yield chunk
