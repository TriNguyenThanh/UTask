from uuid import UUID, uuid4

import pytest

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, ProjectMember


@pytest.mark.integration
@pytest.mark.django_db
def test_project_create_with_local_classroom_enforces_leader_and_persists(settings, client_for):
    settings.CLASSROOM_DEV_ENABLED = True
    settings.CLASSROOM_ADAPTER = "infrastructure.classroom_dev.LocalClassroom"
    leader_id = UUID("24e76a06-0401-4e90-a2f5-1d38d993e6e9")
    payload = {"identifier": "DEV01", "name": "Project dev", "classroom_group_id": "group-example"}
    denied = client_for(uuid4()).post(
        "/api/v1/projects/", payload, format="json", HTTP_IDEMPOTENCY_KEY="dev-outsider"
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "LEADER_PERMISSION_REQUIRED"
    assert not Project.objects.exists()
    leader = client_for(leader_id)
    created = leader.post(
        "/api/v1/projects/", payload, format="json", HTTP_IDEMPOTENCY_KEY="dev-project"
    )
    assert created.status_code == 201
    project = Project.objects.get(pk=created.json()["data"]["id"])
    assert project.classroom_group_id == "group-example" and project.class_id == "class-dev-01"
    assert ProjectMember.objects.filter(project=project, user_id=leader_id, role="LEADER").exists()
    assert project.states.count() == 5
    assert (
        Activity.objects.count()
        == OutboxEvent.objects.count()
        == IdempotencyRecord.objects.count()
        == 1
    )
    assert leader.get(f"/api/v1/projects/{project.id}/").json()["data"]["id"] == str(project.id)
    replay = leader.post(
        "/api/v1/projects/", payload, format="json", HTTP_IDEMPOTENCY_KEY="dev-project"
    )
    assert replay.json() == created.json()
    assert Project.objects.count() == Activity.objects.count() == OutboxEvent.objects.count() == 1
