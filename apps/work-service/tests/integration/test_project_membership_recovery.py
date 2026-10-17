from dataclasses import replace
from uuid import uuid4

import pytest
from django.db import OperationalError
from django.utils import timezone

from apps.messaging.classroom_consumer import consume_classroom_event
from apps.messaging.models import ConsumedEvent
from apps.projects.models import Project
from apps.projects.tasks import recover_active_memberships, recover_project_membership
from tests.fixtures.classroom import membership_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_service_recovery_catches_membership_change_before_project_exists(
    project_payload, actors, client_for, group, classroom, monkeypatch
):
    snapshot = replace(group, group_id=str(uuid4()), class_id=str(uuid4()))
    incoming = replace(snapshot, source_version=4)
    assert not Project.objects.exists()
    assert consume_classroom_event(membership_event(incoming)) is False
    assert not ConsumedEvent.objects.exists()

    # The create request already obtained version 1 before the group changed.
    # Kafka has no existing Project to update, so creation must schedule recovery.
    classroom.groups[snapshot.group_id] = snapshot
    ids = []
    for identifier in ("EARLY1", "EARLY2"):
        response = client_for(actors["leader"]).post(
            "/projects/",
            project_payload | {"identifier": identifier, "classroom_group_id": snapshot.group_id},
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"recovery-{identifier}",
        )
        assert response.status_code == 201
        ids.append(response.json()["data"]["id"])
    assert set(Project.objects.values_list("group_source_version", flat=True)) == {1}
    seen = []

    class Classroom:
        def recovery_snapshot(self, group_id):
            seen.append(group_id)
            return incoming

    monkeypatch.setattr("apps.projects.tasks.classroom_client", Classroom)
    assert recover_project_membership.run(str(ids[0]))
    assert Project.objects.get(pk=ids[0]).group_source_version == 4
    assert seen == [incoming.group_id]
    # The periodic sweep repairs a missed after-commit enqueue for the second project.
    assert recover_active_memberships.run() == {"failed": 0}
    assert set(Project.objects.values_list("group_source_version", flat=True)) == {4}
    Project.objects.update(archived_at=timezone.now())
    seen.clear()
    assert recover_project_membership.run(str(ids[0])) is False
    assert recover_active_memberships.run() == {"failed": 0}
    assert seen == []


def test_recovery_sweep_continues_after_one_project_failure(classroom_projects, monkeypatch):
    ids, _ = classroom_projects
    seen = []

    def recover(project_id):
        seen.append(project_id)
        if project_id == str(ids[0]):
            raise OperationalError("isolated test failure")

    monkeypatch.setattr("apps.projects.tasks.recover_project_membership.run", recover)
    assert recover_active_memberships.run() == {"failed": 1}
    assert set(seen) == {str(project_id) for project_id in ids}


def test_creation_schedules_recovery_only_after_commit_and_sends_only_project_id(
    client_for, actors, project_payload, django_capture_on_commit_callbacks, monkeypatch
):
    calls = []
    monkeypatch.setattr("apps.projects.tasks.recover_project_membership.delay", calls.append)
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(actors["leader"]).post(
            "/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="recovery"
        )
        assert response.status_code == 201
        assert calls == []
    assert calls == [response.json()["data"]["id"]]
