"""Target và input của ba intent phase 1."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from .common import Intent, StrictModel


class ProjectTarget(StrictModel):
    type: Literal["project"]
    id: UUID


class TaskTarget(StrictModel):
    type: Literal["task"]
    id: UUID


class SprintTarget(StrictModel):
    type: Literal["sprint"]
    id: UUID


class BacklogInput(StrictModel):
    description: str = Field(min_length=1, max_length=12_000)
    goals: list[str] = Field(default_factory=list, max_length=30)
    tech_stack: list[str] = Field(default_factory=list, max_length=30)
    deadline: datetime | None = None
    constraints: list[str] = Field(default_factory=list, max_length=30)
    additional_instruction: str | None = Field(default=None, max_length=4_000)


class TaskDecompositionInput(StrictModel):
    task_description: str | None = Field(default=None, min_length=1, max_length=12_000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    additional_instruction: str | None = Field(default=None, max_length=4_000)


class AnalysisWindow(StrictModel):
    from_: datetime = Field(alias="from")
    to: datetime


class RiskAnalysisInput(StrictModel):
    analysis_window: AnalysisWindow | None = None
    focus: list[Literal["deadline", "blocked_task", "github_activity", "progress"]] = Field(
        default_factory=list, max_length=10
    )


class BacklogGenerationRequest(StrictModel):
    intent: Literal[Intent.BACKLOG_GENERATION]
    target: ProjectTarget | None = None
    input: BacklogInput
    output_schema_version: str = "backlog_generation.v1"


class TaskDecompositionRequest(StrictModel):
    intent: Literal[Intent.TASK_DECOMPOSITION]
    target: TaskTarget
    input: TaskDecompositionInput
    output_schema_version: str = "task_decomposition.v1"


class RiskAnalysisRequest(StrictModel):
    intent: Literal[Intent.RISK_ANALYSIS]
    target: ProjectTarget | SprintTarget
    input: RiskAnalysisInput
    output_schema_version: str = "risk_analysis.v1"


CreateAiRequest = Annotated[
    BacklogGenerationRequest | TaskDecompositionRequest | RiskAnalysisRequest,
    Field(discriminator="intent"),
]
