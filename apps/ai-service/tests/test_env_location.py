"""Settings đọc giá trị .env root, tách khỏi biểu thức ánh xạ Compose."""

import runpy
from pathlib import Path

import pytest
from pydantic import ValidationError

import config


def test_settings_reads_central_env_and_preserves_environment_precedence(tmp_path, monkeypatch):
    source = tmp_path / "checkout" / "apps" / "ai-service" / "src" / "config.py"
    source.parent.mkdir(parents=True)
    source.write_text(Path(config.__file__).read_text())
    env_file = tmp_path / "checkout" / "infra" / "env" / "ai-service.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "AI_MODEL=${AI_MODEL:-mapping-model}\n"
        "AI_MAX_MODEL_CALLS=0\n"
        "AI_JWT_ISSUER=${AI_JWT_ISSUER:-${IDENTITY_JWT_ISSUER:-invalid-mapping}}\n"
    )
    secret_file = tmp_path / "checkout" / ".env"
    secret_file.write_text(
        "AI_LLM_API_KEY=local-test-key\nAI_MODEL=root-model\nAI_MAX_MODEL_CALLS=2\n"
    )
    monkeypatch.chdir(tmp_path)
    relocated_settings = runpy.run_path(str(source))["Settings"]
    settings = relocated_settings()
    assert settings.model == "root-model" and settings.max_model_calls == 2
    assert settings.llm_api_key.get_secret_value() == "local-test-key"
    assert settings.jwt_issuer == "https://identity.utask.internal"
    assert "local-test-key" not in repr(settings)
    monkeypatch.setenv("AI_MODEL", "environment-model")
    assert relocated_settings().model == "environment-model"
    secret_file.write_text("AI_MAX_MODEL_CALLS=0\n")
    with pytest.raises(ValidationError):
        relocated_settings()
    secret_file.unlink()
    assert relocated_settings().max_model_calls == 4


@pytest.mark.parametrize("ai_value", [None, "", "https://ai.example/issuer"])
def test_jwt_configuration_uses_identity_fallback_and_explicit_ai_override(
    tmp_path, monkeypatch, ai_value
):
    for key in ("AI_JWT_ISSUER", "AI_JWT_AUDIENCE", "IDENTITY_JWT_ISSUER", "IDENTITY_JWT_AUDIENCE"):
        monkeypatch.delenv(key, raising=False)
    root_env = tmp_path / ".env"
    contents = (
        "IDENTITY_JWT_ISSUER=https://identity.example/issuer\nIDENTITY_JWT_AUDIENCE=identity\n"
    )
    if ai_value is not None:
        contents += f"AI_JWT_ISSUER={ai_value}\nAI_JWT_AUDIENCE={'ai' if ai_value else ''}\n"
    root_env.write_text(contents)
    settings = config.Settings(_env_file=root_env)
    assert settings.jwt_issuer == (ai_value or "https://identity.example/issuer")
    assert settings.jwt_audience == ("ai" if ai_value else "identity")
    monkeypatch.setenv("AI_JWT_ISSUER", "https://process.example/issuer")
    monkeypatch.setenv("AI_JWT_AUDIENCE", "process")
    settings = config.Settings(_env_file=root_env)
    assert settings.jwt_issuer == "https://process.example/issuer"
    assert settings.jwt_audience == "process"
    monkeypatch.delenv("AI_JWT_ISSUER")
    monkeypatch.delenv("AI_JWT_AUDIENCE")
    monkeypatch.setenv("IDENTITY_JWT_ISSUER", "https://process-identity.example/issuer")
    monkeypatch.setenv("IDENTITY_JWT_AUDIENCE", "process-identity")
    settings = config.Settings(_env_file=root_env)
    assert settings.jwt_issuer == "https://process-identity.example/issuer"
    assert settings.jwt_audience == "process-identity"
