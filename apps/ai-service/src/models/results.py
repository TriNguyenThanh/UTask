"""Đề xuất có cấu trúc; chưa bao gồm bước áp dụng vào nghiệp vụ."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import StrictModel


class BacklogItem(StrictModel):
    type: Literal["task"]
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"]
    estimate_points: float = Field(ge=0)
    dependencies: list[str]
    acceptance_criteria: list[str]
    rationale: str


class BacklogResult(StrictModel):
    items: list[BacklogItem] = Field(max_length=100)
    warnings: list[str]


class Subtask(StrictModel):
    title: str
    description: str
    acceptance_criteria: list[str]
    dependencies: list[str]
    estimate_points: float = Field(ge=0)


class TaskDecompositionResult(StrictModel):
    subtasks: list[Subtask] = Field(max_length=50)
    warnings: list[str]


class RiskEvidence(StrictModel):
    source_type: Literal["progress_metric", "task", "sprint", "github_activity"]
    source_id: str
    observed_at: datetime


class Risk(StrictModel):
    code: str
    level: Literal["low", "medium", "high", "critical"]
    title: str
    reason: str
    evidence: list[RiskEvidence]
    suggested_actions: list[str]


class RiskAnalysisResult(StrictModel):
    overall_level: Literal["none", "low", "medium", "high", "critical", "unknown"]
    risks: list[Risk] = Field(max_length=50)
    limitations: list[str]


AiResult = BacklogResult | TaskDecompositionResult | RiskAnalysisResult
