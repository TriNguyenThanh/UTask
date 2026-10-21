import pytest
from pydantic import SecretStr

from config import WORK_CONTEXT_PAIRS, Settings
from errors import ServiceError
from infrastructure.providers import build_litellm_model


def model_settings(**overrides):
    values = {
        "model": "openai/example-model",
        "llm_api_base": "https://llm.example.test/v1",
        "llm_api_key": "test-api-key",
        "work_service_key": "test-work-key",
        "authorization_urls": {
            kind: "https://work/authorize/{target_id}" for kind in ("project", "task", "sprint")
        },
        "context_urls": {pair: "https://work/context/{target_id}" for pair in WORK_CONTEXT_PAIRS},
    }
    values.update(overrides)
    return Settings(**values)


def test_custom_openai_compatible_provider_is_configured_explicitly(monkeypatch):
    captured = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("infrastructure.providers.LiteLlm", FakeLiteLlm)
    model = build_litellm_model(model_settings())
    assert isinstance(model, FakeLiteLlm)
    assert captured == {
        "model": "openai/example-model",
        "api_base": "https://llm.example.test/v1",
        "api_key": "test-api-key",
        "num_retries": 0,
        "max_retries": 0,
        "response_format": {"type": "json_object"},
    }
    assert "test-api-key" not in repr(model)


def test_model_alias_from_local_proxy_gets_openai_prefix(monkeypatch):
    captured = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("infrastructure.providers.LiteLlm", FakeLiteLlm)
    build_litellm_model(model_settings(model="gemini-3.8-flash-high"))
    assert captured["model"] == "openai/gemini-3.8-flash-high"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"model": None}, "AI_MODEL_REQUIRED"),
        ({"model": "openai/"}, "LITELLM_OPENAI_MODEL_REQUIRED"),
        ({"llm_api_base": None}, "AI_LLM_API_BASE_REQUIRED"),
        ({"llm_api_key": None}, "AI_LLM_API_KEY_REQUIRED"),
        ({"llm_api_key": "  "}, "AI_LLM_API_KEY_REQUIRED"),
    ],
)
def test_missing_or_unsupported_provider_configuration_fails_closed(overrides, reason):
    with pytest.raises(ServiceError) as error:
        build_litellm_model(model_settings(**overrides))
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert error.value.details == {"reason": reason}
    assert not error.value.retryable


@pytest.mark.parametrize(
    "api_base,environment",
    [
        ("ftp://llm.example.test/v1", "development"),
        ("https://user:password@llm.example.test/v1", "development"),
        ("https://llm.example.test/v1?token=secret", "development"),
        ("https://llm.example.test:invalid/v1", "development"),
        ("https://llm example.test/v1", "development"),
        ("http://localhost:1234/v1", "production"),
    ],
)
def test_custom_provider_endpoint_must_be_safe(api_base, environment):
    with pytest.raises(ServiceError) as error:
        build_litellm_model(model_settings(llm_api_base=api_base, environment=environment))
    assert error.value.details == {"reason": "AI_LLM_API_BASE_INVALID"}


def test_development_can_use_local_http_endpoint(monkeypatch):
    captured = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("infrastructure.providers.LiteLlm", FakeLiteLlm)
    build_litellm_model(model_settings(llm_api_base="http://localhost:1234/v1"))
    assert captured["api_base"] == "http://localhost:1234/v1"


def test_development_can_use_http_endpoint_on_host_from_docker(monkeypatch):
    captured = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("infrastructure.providers.LiteLlm", FakeLiteLlm)
    build_litellm_model(model_settings(llm_api_base="http://host.docker.internal:8317/v1"))
    assert captured["api_base"] == "http://host.docker.internal:8317/v1"


def test_empty_dotenv_values_are_treated_as_unconfigured(tmp_path):
    path = tmp_path / "ai-service.env"
    path.write_text("AI_MODEL=\nAI_LLM_API_BASE=\nAI_LLM_API_KEY=\n")
    settings = Settings(_env_file=path)
    assert settings.model is None
    assert settings.llm_api_base is None
    assert settings.llm_api_key is None


def test_provider_key_uses_secret_type():
    assert isinstance(model_settings().llm_api_key, SecretStr)
