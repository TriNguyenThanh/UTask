from uuid import uuid4

import pytest

from apps.messaging.models import OutboxEvent
from apps.projects.models import Project

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_uppercase_group_uuid_creates_project_with_canonical_group_id(
    client_for, actors, project_payload, settings, monkeypatch
):
    settings.CLASSROOM_ADAPTER = "infrastructure.classroom.RemoteClassroom"
    group_id = "abcdefab-1234-1234-1234-123456789abc"

    def snapshot(self, path, *, actor):
        assert path == f"/internal/groups/{group_id}/snapshot/"
        assert actor.id == actors["leader"] and actor.access_token
        return {
            "group_id": group_id,
            "class_id": str(uuid4()),
            "source_version": 1,
            "members": [{"user_id": str(actor.id), "role": "LEADER", "status": "ACTIVE"}],
        }

    monkeypatch.setattr("infrastructure.classroom.RemoteClassroom._request", snapshot)
    response = client_for(actors["leader"]).post(
        "/projects/",
        project_payload | {"classroom_group_id": group_id.upper()},
        format="json",
        HTTP_IDEMPOTENCY_KEY="uppercase-group-id",
    )
    assert response.status_code == 201
    assert response.json()["data"]["classroom_group_id"] == group_id
    assert Project.objects.get().classroom_group_id == group_id


def test_invalid_group_uuid_is_user_validation_without_side_effects(
    client_for, actors, project_payload, settings, monkeypatch
):
    settings.CLASSROOM_ADAPTER = "infrastructure.classroom.RemoteClassroom"

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Invalid group ID must not reach Classroom")

    monkeypatch.setattr("infrastructure.classroom.requests.request", unexpected_request)
    response = client_for(actors["leader"]).post(
        "/projects/",
        project_payload | {"classroom_group_id": "not-a-uuid"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="invalid-group-id",
    )
    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": "classroom_group_id", "issue": "Mã nhóm học tập phải hợp lệ."}],
    }
    assert not Project.objects.exists() and not OutboxEvent.objects.exists()
