"""Cấu hình riêng cho API, dispatcher và worker của cùng AI Service."""

from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = (Path(__file__).resolve().parents[1] / "../..").resolve()
ENV_DIR = ROOT_DIR / "infra" / "env"
WORK_CONTEXT_PAIRS = frozenset(
    f"{target}:{domain}"
    for target in ("project", "task", "sprint")
    for domain in ("project", "team", "progress")
) | {"task:task"}


def valid_internal_url(template: str) -> bool:
    """Chỉ chấp nhận URL cấu hình tĩnh với hai placeholder target đã biết."""
    try:
        fields = list(Formatter().parse(template))
        if any(
            name is not None and (name not in {"target_type", "target_id"} or spec or conversion)
            for _, name, spec, conversion in fields
        ):
            return False
        parts = urlsplit(template.format(target_type="project", target_id="target"))
        return (
            not any(character.isspace() for character in template)
            and parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and (parts.port is None or 1 <= parts.port <= 65535)
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and "{" not in urlsplit(template).netloc
        )
    except (ValueError, KeyError, IndexError):
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=(ENV_DIR / "ai-service.env", ROOT_DIR / ".env"),
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
        env_ignore_empty=True,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    mock_test: bool = Field(default=False, validation_alias="MOCK_TEST")
    llm_provider: Literal["litellm"] = "litellm"
    llm_api_key: SecretStr | None = None
    llm_api_base: str | None = None
    app_name: str = "utask-ai-service"
    database_url: str = "postgresql+psycopg://localhost/ai_context_db"
    broker_url: str = "redis://localhost:6379/0"
    credential_key: SecretStr | None = None
    jwt_issuer: str = "https://identity.utask.internal"
    jwt_audience: str = "utask-platform"
    jwt_algorithm: str = "RS256"
    identity_base_url: str = "http://identity-service:8000"
    identity_service_key: SecretStr | None = None
    model: str | None = Field(default=None, min_length=1, pattern=r"^\S+$")
    sync_timeout_seconds: float = Field(default=10, gt=0, le=10)
    workflow_timeout_seconds: float = Field(default=30, gt=0, le=30)
    poll_interval_seconds: float = Field(default=0.1, gt=0)
    completion_reconcile_seconds: float = Field(default=5, gt=0)
    terminal_retention_days: int = Field(default=30, gt=0)
    retention_batch_size: int = Field(default=500, gt=0, le=500)
    retention_interval_seconds: float = Field(default=3600, gt=0)
    queue_timeout_seconds: float = Field(default=300, gt=0)
    requests_per_minute: int = Field(default=5, ge=1)
    max_active_requests_per_user: int = Field(default=2, ge=1)
    max_model_calls: int = Field(default=4, ge=1)
    max_context_tool_calls: int = Field(default=5, ge=0)
    max_output_tokens: int = Field(default=4000, ge=1)
    max_revisions: int = Field(default=1, ge=0, le=3)
    max_dispatch_attempts: int = Field(default=8, ge=1)
    dispatch_lease_seconds: float = Field(default=10, gt=0)
    dispatch_interval_seconds: float = Field(default=1, gt=0)
    redelivery_seconds: float = Field(default=15, gt=0)
    http_timeout_seconds: float = Field(default=3, gt=0, le=10)
    max_context_bytes: int = Field(default=65_536, ge=1024, le=65_536)
    context_max_age_seconds: int = Field(default=300, ge=1)
    # Ánh xạ URL theo contract Work/Integration; agent không nhận URL tùy ý.
    authorization_urls: dict[str, str] = Field(default_factory=dict)
    context_urls: dict[str, str] = Field(default_factory=dict)
    work_service_key: SecretStr | None = None
    work_service_auth_enabled: bool = False
    integration_service_key: SecretStr | None = None
    github_context_enabled: bool = False

    @model_validator(mode="after")
    def safe_configuration(self) -> "Settings":
        if self.jwt_algorithm != "RS256":
            raise ValueError("Chỉ hỗ trợ access token RS256 như Work Service")
        if not valid_internal_url(self.identity_base_url) or "{" in self.identity_base_url:
            raise ValueError("AI_IDENTITY_BASE_URL không hợp lệ")
        if self.mock_test and self.environment not in {"development", "test"}:
            raise ValueError("MOCK_TEST chỉ được bật trong development/test")
        templates = [*self.authorization_urls.values(), *self.context_urls.values()]
        if any(not valid_internal_url(template) for template in templates):
            raise ValueError("URL nội bộ hoặc placeholder không hợp lệ")
        if self.environment in {"staging", "production"}:
            if not self.jwt_issuer or not self.jwt_issuer.strip():
                raise ValueError("AI_JWT_ISSUER là bắt buộc")
            if not self.jwt_audience or not self.jwt_audience.strip():
                raise ValueError("AI_JWT_AUDIENCE là bắt buộc")
            if (
                not self.identity_service_key
                or not self.identity_service_key.get_secret_value().strip()
            ):
                raise ValueError("AI_IDENTITY_SERVICE_KEY là bắt buộc")
            if not self.credential_key:
                raise ValueError("AI_CREDENTIAL_KEY là bắt buộc")
            try:
                Fernet(self.credential_key.get_secret_value().encode())
            except (ValueError, TypeError) as error:
                raise ValueError("AI_CREDENTIAL_KEY phải là khóa Fernet hợp lệ") from error
            if self.work_service_auth_enabled and (
                not self.work_service_key or not self.work_service_key.get_secret_value().strip()
            ):
                raise ValueError("AI_WORK_SERVICE_KEY là bắt buộc")
            if not {"project", "task", "sprint"} <= self.authorization_urls.keys():
                raise ValueError("Thiếu URL authorize cho project/task/sprint")
            if not WORK_CONTEXT_PAIRS <= self.context_urls.keys():
                raise ValueError("Thiếu URL context Work theo target/domain")
            if self.github_context_enabled and (
                not self.context_urls.get("project:github_activity")
                or not self.integration_service_key
                or not self.integration_service_key.get_secret_value().strip()
            ):
                raise ValueError("GitHub context cần URL Integration và AI_INTEGRATION_SERVICE_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
