"""Provider configuration — the part that rots when vendors retire models."""

from app.config import Settings
from app.providers.llm import PROVIDER_SPECS, available_providers


def test_no_keys_means_no_providers():
    assert available_providers(Settings(_env_file=None)) == []


def test_priority_order_filters_to_available_keys():
    s = Settings(_env_file=None, gemini_api_key="g", mistral_api_key="m")
    assert available_providers(s) == ["gemini", "mistral"]

    # default order is gemini,mistral,deepseek (DeepSeek's 2026 peak pricing)
    s = Settings(_env_file=None, deepseek_api_key="d", mistral_api_key="m")
    assert available_providers(s) == ["mistral", "deepseek"]


def test_provider_order_is_configurable():
    s = Settings(
        _env_file=None,
        llm_providers="mistral,deepseek",
        deepseek_api_key="d",
        mistral_api_key="m",
    )
    assert available_providers(s) == ["mistral", "deepseek"]


def test_unknown_provider_names_are_ignored():
    s = Settings(_env_file=None, llm_providers="grok,deepseek", deepseek_api_key="d")
    assert available_providers(s) == ["deepseek"]


def test_every_spec_resolves_key_and_model_from_settings():
    s = Settings(_env_file=None)
    for spec in PROVIDER_SPECS.values():
        assert hasattr(s, spec.key_attr), spec.name
        model = getattr(s, spec.model_attr)
        assert isinstance(model, str) and model, spec.name


def test_current_model_defaults():
    """Pin the defaults so a future edit is a conscious choice.
    deepseek-chat and grok-3-mini both retired in 2026 — model IDs rot."""
    s = Settings(_env_file=None)
    assert s.deepseek_model == "deepseek-v4-flash"
    assert s.gemini_model == "gemini-3.5-flash-lite"
    assert s.mistral_model == "mistral-small-latest"
