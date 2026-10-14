"""Target và input của ba intent phase 1."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

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

    @model_validator(mode="after")
    def valid_range(self):
        if self.from_.tzinfo is None or self.to.tzinfo is None or self.from_ > self.to:
            raise ValueError("analysis_window phải có múi giờ và from <= to")
        return self


class RiskAnalysisInput(StrictModel):
    analysis_window: AnalysisWindow | None = None
    focus: list[Literal["deadline", "blocked_task", "github_activity", "progress"]] = Field(
        default_factory=list, max_length=10
    )


class BacklogGenerationRequest(StrictModel):
    intent: Literal[Intent.BACKLOG_GENERATION]
    target: ProjectTarget | None = None
    input: BacklogInput
    output_schema_version: Literal["backlog_generation.v1", "current"] = "backlog_generation.v1"

    @model_validator(mode="after")
    def normalize_version(self):
        if self.output_schema_version == "current":
            self.output_schema_version = f"{self.intent}.v1"
        return self


class TaskDecompositionRequest(StrictModel):
    intent: Literal[Intent.TASK_DECOMPOSITION]
    target: TaskTarget
    input: TaskDecompositionInput
    output_schema_version: Literal["task_decomposition.v1", "current"] = "task_decomposition.v1"

    @model_validator(mode="after")
    def normalize_version(self):
        if self.output_schema_version == "current":
            self.output_schema_version = f"{self.intent}.v1"
        return self


class RiskAnalysisRequest(StrictModel):
    intent: Literal[Intent.RISK_ANALYSIS]
    target: ProjectTarget | SprintTarget
    input: RiskAnalysisInput
    output_schema_version: Literal["risk_analysis.v1", "current"] = "risk_analysis.v1"

    @model_validator(mode="after")
    def normalize_version(self):
        if self.output_schema_version == "current":
            self.output_schema_version = f"{self.intent}.v1"
        return self


CreateAiRequest = Annotated[
    BacklogGenerationRequest | TaskDecompositionRequest | RiskAnalysisRequest,
    Field(discriminator="intent"),
]
