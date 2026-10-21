"""Envelope context và dữ liệu domain theo contract Work/Integration đã chốt."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictFloat, StrictInt, StrictStr

from .common import StrictModel


class ContextDocument(StrictModel):
    domain: Literal["project", "task", "team", "progress", "github_activity", "sprint"]
    as_of: datetime
    status: Literal["available", "partial", "missing", "stale", "unavailable"]
    source_version: str | None = None
    data: dict[str, object] = Field(default_factory=dict)
    warning: str | None = None


Identifier = Annotated[
    StrictStr,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
Text = Annotated[StrictStr, Field(max_length=4000)]
ShortText = Annotated[StrictStr, Field(max_length=300)]
Name = Annotated[StrictStr, Field(max_length=200)]
State = Annotated[StrictStr, Field(max_length=100)]
Number = Annotated[StrictFloat, Field(allow_inf_nan=False)]
NonnegativeNumber = Annotated[Number, Field(ge=0)]
Count = Annotated[StrictInt, Field(ge=0)]


class TaskSummary(StrictModel):
    id: Identifier
    title: ShortText
    status: State
    priority: State = Field(default=None)
    deadline: date | None = None
    estimate_points: NonnegativeNumber | None = None


class SprintSummary(StrictModel):
    id: Identifier
    name: Name
    status: Literal["DRAFT", "ACTIVE", "COMPLETED"]
    deadline: date | None


class ProjectContextData(StrictModel):
    id: Identifier
    name: Name
    description: Text
    goals: Text
    deadline: date | None
    tasks: list[TaskSummary] = Field(max_length=100)
    sprints: list[SprintSummary] = Field(max_length=100)


class TaskContextData(StrictModel):
    id: Identifier
    project_id: Identifier
    title: ShortText
    description: Text
    status: State
    priority: State
    deadline: date | None
    estimate_points: NonnegativeNumber | None
    dependencies: list[Identifier] = Field(max_length=100)
    acceptance_criteria: Text


class TeamMemberContext(StrictModel):
    user_id: Identifier
    capacity: NonnegativeNumber
    workload: NonnegativeNumber


class TeamContextData(StrictModel):
    members: list[TeamMemberContext] = Field(max_length=100)
    capacity: NonnegativeNumber
    workload: NonnegativeNumber


class ProgressMetric(StrictModel):
    name: State
    value: Number | None
    unit: State
    observed_at: AwareDatetime


class ProgressContextData(StrictModel):
    metrics: list[ProgressMetric] = Field(max_length=100)
    blocked_tasks: list[TaskSummary] = Field(max_length=100)
    completed_tasks: Count
    total_tasks: Count
    as_of: AwareDatetime


class GitHubActivityItem(StrictModel):
    id: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    title: ShortText | None
    status: Annotated[StrictStr, Field(max_length=40)] | None
    url: Annotated[
        StrictStr,
        Field(max_length=1000, pattern=r"^https://github\.com/[^?#\s\\]+$"),
    ]
    occurred_at: AwareDatetime


class GitHubContextData(StrictModel):
    commits: list[GitHubActivityItem] = Field(max_length=20)
    pull_requests: list[GitHubActivityItem] = Field(max_length=20)
    issues: list[GitHubActivityItem] = Field(max_length=20)
    mapping_status: Literal["CONNECTED", "DISCONNECTED", "REAUTH_REQUIRED"]


CONTEXT_DATA_SCHEMAS = {
    "project": ProjectContextData,
    "task": TaskContextData,
    "team": TeamContextData,
    "progress": ProgressContextData,
    "github_activity": GitHubContextData,
}
