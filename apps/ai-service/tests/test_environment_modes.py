import json

import jwt
import pytest
from conftest import identity_transport
from dotenv import dotenv_values
from pydantic import ValidationError
from pydantic_settings import SettingsError

from config import WORK_CONTEXT_PAIRS, Settings
from infrastructure.context_fixtures import FixtureContextAdapter
from scripts.setup_mock import main, prepare_mock_environment


@pytest.mark.parametrize("environment", ["development", "test"])
def test_mock_mode_is_allowed_only_in_local_environments(environment):
    settings = Settings(environment=environment, mock_test=True)
    assert isinstance(FixtureContextAdapter(settings), FixtureContextAdapter)
    assert set(settings.authorization_urls) == {"project", "task", "sprint"}
    assert set(settings.context_urls) == WORK_CONTEXT_PAIRS


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_default_work_routes_are_ready_without_url_environment(environment):
    settings = Settings(environment=environment, identity_service_key="test-identity-key")
    prefix = "http://work-service:8000/api/v1/internal/ai/targets/"
    for target, template in settings.authorization_urls.items():
        assert template.format(target_type=target, target_id="target-id") == (
            f"{prefix}{target}/target-id/authorize"
        )
    for pair, template in settings.context_urls.items():
        target, domain = pair.split(":")
        assert template.format(target_type=target, target_id="target-id") == (
            f"{prefix}{target}/target-id/contexts/{domain}"
        )
    settings.context_urls.clear()
    assert set(Settings().context_urls) == WORK_CONTEXT_PAIRS


@pytest.mark.parametrize("value", [None, "", "{}", '{"project":"https://work.example/path"}'])
def test_url_environment_overrides_and_empty_values(monkeypatch, value):
    for key in ("AI_AUTHORIZATION_URLS", "AI_CONTEXT_URLS"):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    settings = Settings()
    if value:
        assert settings.authorization_urls == settings.context_urls == json.loads(value)
    else:
        assert set(settings.authorization_urls) == {"project", "task", "sprint"}
        assert set(settings.context_urls) == WORK_CONTEXT_PAIRS


@pytest.mark.parametrize("key", ["AI_AUTHORIZATION_URLS", "AI_CONTEXT_URLS"])
@pytest.mark.parametrize(
    "value,error",
    [
        ("invalid-json", SettingsError),
        ('{"project":"http://user:password@work/context"}', ValidationError),
    ],
)
def test_url_environment_rejects_invalid_json_or_unsafe_url(monkeypatch, key, value, error):
    monkeypatch.setenv(key, value)
    with pytest.raises(error):
        Settings()


@pytest.mark.parametrize("environment", ["staging", "production", "invalid"])
def test_mock_mode_rejects_non_local_environments(environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment, mock_test=True)


def test_mock_false_keeps_real_urls_and_rejects_fixture_adapter():
    from config import WORK_CONTEXT_PAIRS

    settings = Settings(
        environment="production",
        mock_test=False,
        jwt_issuer="https://identity.utask.internal",
        jwt_audience="utask-platform",
        identity_service_key="test-identity-key",
        context_urls={key: "http://work/context/{target_id}" for key in WORK_CONTEXT_PAIRS},
        authorization_urls={
            key: "http://work/authorize/{target_id}" for key in ("project", "task", "sprint")
        },
        work_service_key="test-work-key",
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


@pytest.mark.parametrize("legacy_db_password", [None, "legacy-db-password"])
async def test_setup_and_refresh_preserve_secrets_and_issue_valid_jwt(tmp_path, legacy_db_password):
    from infrastructure.security import JwtAuthenticator

    (tmp_path / ".env").write_text(
        "AI_LLM_API_KEY=existing-key\nGOOGLE_API_KEY=legacy-key\nOTHER_SECRET=keep\n"
        "POSTGRES_PASSWORD=existing-db-password\n"
        + (f"AI_DB_PASSWORD={legacy_db_password}\n" if legacy_db_password else "")
    )
    config = tmp_path / "infra/env/ai-service.env"
    config.parent.mkdir(parents=True)
    mapping = "AI_ENVIRONMENT=${AI_ENVIRONMENT:-development}\nMOCK_TEST=${MOCK_TEST:-false}\n"
    config.write_text(mapping)
    prepare_mock_environment(tmp_path)
    before = dotenv_values(tmp_path / ".env")
    assert "AI_CREDENTIAL_KEY" not in before
    assert before.get("AI_DB_PASSWORD") == legacy_db_password
    settings = Settings(_env_file=tmp_path / ".env", identity_service_key="test-key")
    assert settings.mock_test
    assert settings.jwt_issuer == "utask-local-mock"
    token_path = tmp_path / ".env.mock/mock-owner.jwt"
    assert (
        await JwtAuthenticator(
            settings,
            transport=identity_transport(
                json.loads((tmp_path / ".env.mock/jwks.json").read_text())
            ),
        ).authenticate(token_path.read_text().strip())
    ).user_id == "00000000-0000-4000-8000-000000000001"
    assert (
        jwt.decode(token_path.read_text().strip(), options={"verify_signature": False})[
            "token_type"
        ]
        == "access"
    )
    with pytest.raises(FileExistsError):
        prepare_mock_environment(tmp_path)
    before_jwks = (tmp_path / ".env.mock/jwks.json").read_text()
    prepare_mock_environment(tmp_path, refresh=True)
    after = dotenv_values(tmp_path / ".env")
    for key in [
        "AI_LLM_API_KEY",
        "GOOGLE_API_KEY",
        "POSTGRES_PASSWORD",
        "OTHER_SECRET",
    ]:
        assert before[key] == after[key]
    assert "AI_CREDENTIAL_KEY" not in after
    assert after.get("AI_DB_PASSWORD") == legacy_db_password
    assert before_jwks != (tmp_path / ".env.mock/jwks.json").read_text()
    assert config.read_text() == mapping
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / ".env.mock").stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (tmp_path / ".env.mock").iterdir())


@pytest.mark.parametrize("hours", [0, 25])
def test_setup_rejects_invalid_expiry_without_writing(tmp_path, hours):
    with pytest.raises(ValueError):
        prepare_mock_environment(tmp_path, token_hours=hours)
    assert not (tmp_path / ".env").exists()


def test_setup_does_not_modify_production_or_existing_public_key(tmp_path):
    config = tmp_path / ".env"
    config.write_text("AI_ENVIRONMENT=production\nOTHER_SECRET=keep\n")
    with pytest.raises(ValidationError):
        prepare_mock_environment(tmp_path)
    assert config.read_text() == "AI_ENVIRONMENT=production\nOTHER_SECRET=keep\n"
    assert not (tmp_path / ".env.mock").exists()
    config.write_text("AI_ENVIRONMENT=development\nAI_JWT_PUBLIC_KEY=existing\n")
    with pytest.raises(FileExistsError):
        prepare_mock_environment(tmp_path)
    assert config.read_text() == "AI_ENVIRONMENT=development\nAI_JWT_PUBLIC_KEY=existing\n"


def test_setup_cli_uses_repo_root_and_protects_existing_keys(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.setup_mock.ROOT_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["setup_mock"])
    main()
    assert str(tmp_path / ".env") in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "Không tạo được" in capsys.readouterr().err


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_issuer": None},
        {"jwt_issuer": " "},
        {"jwt_audience": None},
        {"jwt_audience": " "},
        {"identity_service_key": None},
        {"identity_service_key": " "},
        {"authorization_urls": {}},
        {"context_urls": {}},
    ],
)
def test_deployed_environments_reject_missing_auth_configuration(environment, overrides):
    with pytest.raises(ValidationError):
        Settings(**({"environment": environment, "identity_service_key": "test-key"} | overrides))


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_accept_complete_auth_configuration(environment, monkeypatch):
    monkeypatch.delenv("AI_CREDENTIAL_KEY", raising=False)
    settings = Settings(
        environment=environment, identity_service_key="test-key", work_service_key=None
    )
    assert "credential_key" not in type(settings).model_fields
    assert settings.environment == environment
    assert settings.jwt_issuer == "https://identity.utask.internal"
    assert settings.jwt_audience == "utask-platform"
    assert settings.identity_base_url == "http://identity-service:8000"
    assert not settings.work_service_auth_enabled
