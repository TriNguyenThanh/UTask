import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectMember


@pytest.mark.django_db
def test_project_task_context_can_be_created_and_updated():
    client = APIClient()
    project_response = client.post("/api/v1/projects", {"name": "AI context"}, format="json")
    assert project_response.status_code == 201
    project_id = project_response.data["id"]
    ProjectMember.objects.create(
        project=Project.objects.get(id=project_id),
        user_id="identity-user-1",
        display_name="Mai",
        weekly_capacity=8,
    )
    created = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        {
            "title": "Build context",
            "priority": "HIGH",
            "story_points": 5,
            "assignee_ids": ["identity-user-1"],
        },
        format="json",
    )
    assert created.status_code == 201
    changed = client.patch(
        "/api/v1/tasks/{}".format(created.data["id"]), {"status": "IN_PROGRESS"}, format="json"
    )
    assert changed.status_code == 200
    assert changed.data["status"] == "IN_PROGRESS"
    assert (
        client.get(f"/api/v1/projects/{project_id}/members").data[0]["user_id"] == "identity-user-1"
    )
