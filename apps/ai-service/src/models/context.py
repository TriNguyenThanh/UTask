"""Kết quả adapter context; không phải hợp đồng REST giả của service khác."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import StrictModel


class ContextDocument(StrictModel):
    domain: Literal["project", "task", "team", "progress", "github_activity", "sprint"]
    as_of: datetime
    status: Literal["available", "partial", "missing", "stale", "unavailable"]
    source_version: str | None = None
    data: dict[str, object] = Field(default_factory=dict)
    warning: str | None = None
