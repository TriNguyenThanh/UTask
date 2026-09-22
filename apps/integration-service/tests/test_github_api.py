from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_normalized_github_activity_is_available_by_project():
    client = APIClient()
    repository = client.post(
        "/api/v1/integrations/github/repositories",
        {
            "project_id": "work-project-1",
            "github_repository_id": "github-1",
            "full_name": "utask/repository",
        },
        format="json",
    )
    assert repository.status_code == 201
    commit = client.post(
        "/api/v1/integrations/github/repositories/{}/commits".format(repository.data["id"]),
        {
            "sha": "abc123",
            "author_id": "identity-user-1",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        format="json",
    )
    assert commit.status_code == 201
    activity = client.get("/api/v1/projects/work-project-1/github-activity")
    assert activity.status_code == 200
    assert activity.data["commits"][0]["sha"] == "abc123"
