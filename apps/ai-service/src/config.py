"""Cấu hình riêng cho API, dispatcher và worker của cùng AI Service."""

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    app_name: str = "utask-ai-service"
    database_url: str = "postgresql+psycopg://localhost/ai_context_db"
    broker_url: str = "redis://localhost:6379/0"
    credential_key: SecretStr | None = None
    jwt_public_key: str | None = None
    jwt_jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_algorithm: str = "RS256"
    model: str = "gemini-flash-latest"
    sync_timeout_seconds: float = Field(default=10, gt=0, le=10)
    workflow_timeout_seconds: float = Field(default=30, gt=0, le=30)
    poll_interval_seconds: float = Field(default=0.1, gt=0)
    queue_timeout_seconds: float = Field(default=300, gt=0)
    max_model_calls: int = Field(default=4, ge=1)
    max_context_tool_calls: int = Field(default=5, ge=0)
    max_output_tokens: int = Field(default=4000, ge=1)
    max_revisions: int = Field(default=1, ge=0, le=3)
    max_dispatch_attempts: int = Field(default=8, ge=1)
    dispatch_lease_seconds: float = Field(default=10, gt=0)
    dispatch_interval_seconds: float = Field(default=1, gt=0)
    redelivery_seconds: float = Field(default=15, gt=0)
    http_timeout_seconds: float = Field(default=3, gt=0, le=10)
    max_context_bytes: int = Field(default=64_000, ge=1024)
    context_max_age_seconds: int = Field(default=300, ge=1)
    # Không giả định endpoint Work/Integration chưa được công bố.
    authorization_urls: dict[str, str] = Field(default_factory=dict)
    context_urls: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def safe_configuration(self) -> "Settings":
        if self.jwt_algorithm not in {"RS256", "ES256"}:
            raise ValueError("Chỉ hỗ trợ JWT ký bất đối xứng RS256 hoặc ES256")
        if self.jwt_public_key and self.jwt_jwks_url:
            raise ValueError("Chọn public key hoặc JWKS, không dùng cả hai")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
