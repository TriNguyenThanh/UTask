import json
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.request import urlopen

from app.schemas.models import GitHubActivity, ProjectContext, TaskContext


class ContextProvider(ABC):
    @abstractmethod
    def get_project_context(self, project_id: str) -> ProjectContext: ...

    @abstractmethod
    def get_github_activity(self, project_id: str) -> GitHubActivity: ...


class DatasetContextProvider(ContextProvider):
    def __init__(self, datasets_dir: Path):
        self.datasets_dir = datasets_dir

    def _read(self, relative_path: str):
        return json.loads((self.datasets_dir / relative_path).read_text(encoding="utf-8"))

    def get_project_context(self, project_id: str) -> ProjectContext:
        project = self._read("projects/ai-first-project.json")
        if project["id"] != project_id:
            raise KeyError(project_id)
        tasks = [TaskContext(**task) for task in self._read("tasks/overloaded-member.json")]
        return ProjectContext(
            id=project["id"],
            name=project["name"],
            members=project["members"],
            tasks=tasks,
            sprint_end_date=project["sprint"]["end_date"],
        )

    def get_github_activity(self, project_id: str) -> GitHubActivity:
        activity = self._read("github/github-activity-gap.json")
        if activity["project_id"] != project_id:
            raise KeyError(project_id)
        return GitHubActivity(**activity)


class HttpContextProvider(ContextProvider):
    def __init__(self, work_service_url: str, integration_service_url: str):
        self.work_service_url = work_service_url.rstrip("/")
        self.integration_service_url = integration_service_url.rstrip("/")

    def _get(self, url: str):
        with urlopen(url, timeout=5) as response:  # nosec B310: configured internal service URLs only
            return json.loads(response.read().decode("utf-8"))

    def get_project_context(self, project_id: str) -> ProjectContext:
        project = self._get(f"{self.work_service_url}/api/v1/projects/{project_id}")
        members = self._get(f"{self.work_service_url}/api/v1/projects/{project_id}/members")
        tasks = self._get(f"{self.work_service_url}/api/v1/projects/{project_id}/tasks")
        sprints = self._get(f"{self.work_service_url}/api/v1/projects/{project_id}/sprints")
        current_sprint = next((sprint for sprint in sprints if sprint["end_date"]), None)
        return ProjectContext(
            id=str(project["id"]),
            name=project["name"],
            members=members,
            tasks=[
                TaskContext(
                    id=str(task["id"]),
                    title=task["title"],
                    status=task["status"],
                    priority=task["priority"],
                    story_points=task["story_points"],
                    due_date=task["due_date"],
                    assignee_ids=task["assignees"],
                )
                for task in tasks
            ],
            sprint_end_date=current_sprint["end_date"] if current_sprint else None,
        )

    def get_github_activity(self, project_id: str) -> GitHubActivity:
        return GitHubActivity(
            **self._get(
                f"{self.integration_service_url}/api/v1/projects/{project_id}/github-activity"
            )
        )
