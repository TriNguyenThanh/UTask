"""Cấu hình đọc đúng infra/env dù checkout hoặc cwd thay đổi."""

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
    env_file.write_text("AI_MODEL=central-model\nAI_MAX_MODEL_CALLS=2\n")
    secret_file = tmp_path / "checkout" / ".env"
    secret_file.write_text("AI_LLM_API_KEY=local-test-key\nAI_MODEL=root-model\n")
    monkeypatch.chdir(tmp_path)
    relocated_settings = runpy.run_path(str(source))["Settings"]
    settings = relocated_settings()
    assert settings.model == "root-model" and settings.max_model_calls == 2
    assert settings.llm_api_key.get_secret_value() == "local-test-key"
    assert "local-test-key" not in repr(settings)
    monkeypatch.setenv("AI_MODEL", "environment-model")
    assert relocated_settings().model == "environment-model"
    env_file.write_text("AI_MAX_MODEL_CALLS=0\n")
    with pytest.raises(ValidationError):
        relocated_settings()
    env_file.unlink()
    assert relocated_settings().max_model_calls == 4
