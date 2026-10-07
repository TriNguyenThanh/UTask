from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the transport/application bootstrap."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "utask-ai-service"
    environment: str = "local"
    provider: str = Field(default="unconfigured", validation_alias="AI_PROVIDER")
    sync_timeout_seconds: float = Field(default=10.0, gt=0)
    workflow_timeout_seconds: float = Field(default=30.0, gt=0)
    max_model_calls: int = Field(default=4, ge=1)
    max_context_tool_calls: int = Field(default=5, ge=0)
    max_specialist_calls: int = Field(default=1, ge=0)
    max_output_tokens: int = Field(default=4000, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
