"""Regression tests for the LLM factory (`agents.llm.llm_factory`).

Only the provider constructor (`init_chat_model`) is replaced - the factory
itself, its configuration handling and its error messages are the real
implementation.
"""

from __future__ import annotations

import pytest

from agents.llm.llm_factory import LLMConfigurationError, LLMFactory
from core.config import Settings


def make_settings(**overrides) -> Settings:
    """Build an explicit settings object, independent of the local .env."""
    values = {
        "APP_NAME": "test-app",
        "APP_VERSION": "0.0.0",
        "POOL_PRE_PING": True,
        "CONNECT_TIMEOUT": 10,
        "POSTGRES_USERNAME": "postgres",
        "POSTGRES_PASSWORD": "secret",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": 5432,
        "POSTGRES_MAIN_DATABASE": "test",
        "MODEL_ID": "test-model",
        "GENERATION_BACKEND": "OPENAI",
        "OPENAI_API_KEY": "openai-key",
        "OPENAI_API_URL": None,
        "GOOGLE_API_KEY": "gemini-key",
        "DEFAULT_TEMPERATURE": 0.0,
        "DEFAULT_MAX_TOKENS": 800,
        "LLM_TIMEOUT": 60.0,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def captured_model(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the keyword arguments passed to the provider constructor."""
    captured: dict = {"instance": None}

    def _init_chat_model(**kwargs):
        captured.update(kwargs)
        captured["instance"] = object()
        return captured["instance"]

    monkeypatch.setattr(
        "agents.llm.llm_factory.init_chat_model", _init_chat_model
    )
    return captured


# --------------------------------------------------------------------------
# Configuration errors
# --------------------------------------------------------------------------
def test_missing_model_id_is_rejected(captured_model: dict):
    factory = LLMFactory(config=make_settings(MODEL_ID=None))

    with pytest.raises(LLMConfigurationError, match="MODEL_ID must be configured"):
        factory.create()

    assert captured_model == {"instance": None}


def test_missing_openai_api_key_is_rejected(captured_model: dict):
    factory = LLMFactory(config=make_settings(OPENAI_API_KEY=None))

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY is required"):
        factory.create()

    assert captured_model == {"instance": None}


def test_missing_gemini_api_key_is_rejected(captured_model: dict):
    factory = LLMFactory(
        config=make_settings(GENERATION_BACKEND="GEMINI", GOOGLE_API_KEY=None)
    )

    with pytest.raises(LLMConfigurationError, match="GOOGLE_API_KEY is required"):
        factory.create()

    assert captured_model == {"instance": None}


def test_unsupported_backend_is_rejected(captured_model: dict):
    # The Literal type restricts GENERATION_BACKEND to OPENAI/GEMINI, so the
    # unsupported branch is only reachable with an unvalidated settings object.
    settings = Settings.model_construct(
        GENERATION_BACKEND="CURSOR",
        MODEL_ID="test-model",
        DEFAULT_TEMPERATURE=0.0,
        DEFAULT_MAX_TOKENS=None,
        LLM_TIMEOUT=60.0,
        OPENAI_API_KEY="openai-key",
        GOOGLE_API_KEY="gemini-key",
        OPENAI_API_URL=None,
    )
    factory = LLMFactory(config=settings)

    with pytest.raises(LLMConfigurationError, match="Unsupported backend: CURSOR"):
        factory.create()

    assert captured_model == {"instance": None}


# --------------------------------------------------------------------------
# Provider configuration
# --------------------------------------------------------------------------
def test_openai_backend_configuration(captured_model: dict):
    factory = LLMFactory(config=make_settings(GENERATION_BACKEND="OPENAI"))

    factory.create()

    assert captured_model["model"] == "test-model"
    assert captured_model["model_provider"] == "openai"
    assert captured_model["api_key"] == "openai-key"
    assert captured_model["temperature"] == 0.0
    assert captured_model["max_tokens"] == 800
    assert captured_model["timeout"] == 60.0
    assert "base_url" not in captured_model


def test_openai_backend_uses_the_configured_base_url(captured_model: dict):
    factory = LLMFactory(
        config=make_settings(
            GENERATION_BACKEND="OPENAI",
            OPENAI_API_URL="https://example.test/v1",
        )
    )

    factory.create()

    assert captured_model["base_url"] == "https://example.test/v1"
    assert captured_model["model_provider"] == "openai"


def test_gemini_backend_configuration(captured_model: dict):
    factory = LLMFactory(config=make_settings(GENERATION_BACKEND="GEMINI"))

    factory.create()

    assert captured_model["model"] == "test-model"
    assert captured_model["model_provider"] == "google_genai"
    assert captured_model["api_key"] == "gemini-key"
    assert "base_url" not in captured_model


def test_optional_parameters_are_omitted_when_not_configured(captured_model: dict):
    factory = LLMFactory(
        config=make_settings(
            DEFAULT_TEMPERATURE=None,
            DEFAULT_MAX_TOKENS=None,
            LLM_TIMEOUT=None,
        )
    )

    factory.create()

    assert "temperature" not in captured_model
    assert "max_tokens" not in captured_model
    assert "timeout" not in captured_model
    assert captured_model["model"] == "test-model"


def test_factory_falls_back_to_the_application_settings(captured_model: dict):
    from core.config import get_settings

    factory = LLMFactory()

    factory.create()

    assert captured_model["model"] == get_settings().MODEL_ID
    assert captured_model["model_provider"] in ("openai", "google_genai")


def test_created_model_is_the_one_returned_by_the_provider(captured_model: dict):
    model = LLMFactory(config=make_settings()).create()

    assert model is captured_model["instance"]


def test_factory_accepts_a_settings_instance_or_none():
    assert isinstance(LLMFactory(config=make_settings()).config, Settings)
    assert LLMFactory().config is not None
