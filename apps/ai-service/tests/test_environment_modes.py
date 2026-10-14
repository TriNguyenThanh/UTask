import pytest
from dotenv import dotenv_values
from pydantic import ValidationError

from config import Settings
from infrastructure.context_fixtures import FixtureContextAdapter
from scripts.setup_mock import main, prepare_mock_environment


@pytest.mark.parametrize("environment", ["development", "test"])
def test_mock_mode_is_allowed_only_in_local_environments(environment):
    settings = Settings(environment=environment, mock_test=True)
    assert isinstance(FixtureContextAdapter(settings), FixtureContextAdapter)
    assert settings.authorization_urls == settings.context_urls == {}


@pytest.mark.parametrize("environment", ["staging", "production", "invalid"])
def test_mock_mode_rejects_non_local_environments(environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment, mock_test=True)


def test_mock_false_keeps_real_urls_and_rejects_fixture_adapter():
    settings = Settings(
        environment="production",
        mock_test=False,
        context_urls={"task:task": "http://work/context/{target_id}"},
    )
    assert settings.context_urls["task:task"] == "http://work/context/{target_id}"
    with pytest.raises(ValueError):
        FixtureContextAdapter(settings)


def test_environment_flags_and_secret_error_redaction(tmp_path, monkeypatch):
    path = tmp_path / "ai-service.env"
    path.write_text("AI_ENVIRONMENT=development\nMOCK_TEST=TRUE\n")
    assert Settings(_env_file=path).mock_test
    monkeypatch.setenv("MOCK_TEST", "false")
    assert not Settings(_env_file=path).mock_test
    monkeypatch.setenv("MOCK_TEST", "invalid")
    with pytest.raises(ValidationError):
        Settings(_env_file=path)
    with pytest.raises(ValidationError) as error:
        Settings(environment="production", mock_test=True, llm_api_key="sensitive-key")
    assert "sensitive-key" not in str(error.value)


async def test_setup_and_refresh_preserve_secrets_and_issue_valid_jwt(tmp_path):
    from infrastructure.security import JwtAuthenticator

    (tmp_path / ".env").write_text(
        "AI_LLM_API_KEY=existing-key\nGOOGLE_API_KEY=legacy-key\nOTHER_SECRET=keep\n"
    )
    prepare_mock_environment(tmp_path)
    before = dotenv_values(tmp_path / ".env")
    config = tmp_path / "infra/env/ai-service.env"
    settings = Settings(_env_file=(config, tmp_path / ".env"))
    token_path = tmp_path / ".env.mock/mock-owner.jwt"
    assert (
        await JwtAuthenticator(settings).authenticate(token_path.read_text().strip())
    ).user_id == "mock-owner"
    with pytest.raises(FileExistsError):
        prepare_mock_environment(tmp_path)
    prepare_mock_environment(tmp_path, refresh=True)
    after = dotenv_values(tmp_path / ".env")
    for key in [
        "AI_LLM_API_KEY",
        "GOOGLE_API_KEY",
        "AI_DB_PASSWORD",
        "AI_CREDENTIAL_KEY",
        "OTHER_SECRET",
    ]:
        assert before[key] == after[key]
    assert before["AI_JWT_PUBLIC_KEY"] != after["AI_JWT_PUBLIC_KEY"]
    assert "AI_MOCK_DOMAIN_URL" not in dotenv_values(config)
    assert "GOOGLE_API_KEY" not in dotenv_values(config)
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / ".env.mock").stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (tmp_path / ".env.mock").iterdir())


@pytest.mark.parametrize("hours", [0, 25])
def test_setup_rejects_invalid_expiry_without_writing(tmp_path, hours):
    with pytest.raises(ValueError):
        prepare_mock_environment(tmp_path, token_hours=hours)
    assert not (tmp_path / ".env").exists()


def test_setup_does_not_modify_production_or_existing_public_key(tmp_path):
    config = tmp_path / "infra/env/ai-service.env"
    config.parent.mkdir(parents=True)
    config.write_text("AI_ENVIRONMENT=production\n")
    with pytest.raises(ValidationError):
        prepare_mock_environment(tmp_path)
    assert not (tmp_path / ".env").exists()
    config.write_text("AI_ENVIRONMENT=development\n")
    (tmp_path / ".env").write_text("AI_JWT_PUBLIC_KEY=existing\n")
    with pytest.raises(FileExistsError):
        prepare_mock_environment(tmp_path)
    assert (tmp_path / ".env").read_text() == "AI_JWT_PUBLIC_KEY=existing\n"


def test_setup_cli_uses_repo_root_and_protects_existing_keys(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.setup_mock.ROOT_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["setup_mock"])
    main()
    assert str(tmp_path / ".env") in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "Không tạo được" in capsys.readouterr().err
