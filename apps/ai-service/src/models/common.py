"""Kiểu dùng chung cho request, result và response."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Intent(StrEnum):
    BACKLOG_GENERATION = "backlog_generation"
    TASK_DECOMPOSITION = "task_decomposition"
    RISK_ANALYSIS = "risk_analysis"
