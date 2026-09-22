from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskContext(BaseModel):
    id: str
    title: str
    status: str
    priority: Priority
    story_points: int = Field(ge=0)
    due_date: date | None = None
    assignee_ids: list[str] = []


class MemberContext(BaseModel):
    user_id: str
    display_name: str
    weekly_capacity: int = Field(ge=0)


class ProjectContext(BaseModel):
    id: str
    name: str
    members: list[MemberContext]
    tasks: list[TaskContext]
    sprint_end_date: date | None = None


class GitHubCommit(BaseModel):
    sha: str
    author_id: str
    timestamp: datetime


class GitHubPullRequest(BaseModel):
    number: int
    author_id: str
    state: str
    updated_at: datetime


class GitHubActivity(BaseModel):
    project_id: str
    commits: list[GitHubCommit] = []
    pull_requests: list[GitHubPullRequest] = []


class WorkloadMember(BaseModel):
    user_id: str
    assigned_story_points: int
    weekly_capacity: int
    utilization: float
    status: str


class WorkloadAnalysis(BaseModel):
    status: str
    members: list[WorkloadMember]
    recommendations: list[str]
    explanation: str


class RiskFactor(BaseModel):
    code: str
    explanation: str


class ProjectRiskAnalysis(BaseModel):
    status: str
    factors: list[RiskFactor]
    explanation: str


class PrioritySuggestionRequest(BaseModel):
    task: TaskContext
    project: ProjectContext


class PrioritySuggestion(BaseModel):
    suggested_priority: Priority
    explanation: str


class TaskGenerationRequest(BaseModel):
    project_id: str
    objective: str = Field(min_length=1)


class GeneratedTask(BaseModel):
    title: str
    description: str
    suggested_priority: Priority
    estimated_story_points: int = Field(ge=1)


class TaskGenerationSuggestion(BaseModel):
    tasks: list[GeneratedTask]
