from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from apps.projects.models import Project, ProjectMember
from apps.sprints.models import Sprint
from apps.tasks.models import Task
from common.errors import WorkError
from tests.fixtures.ai_context import context_url

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("target_type", ["project", "task", "sprint"])
def test_removed_assignee_loses_access_between_authorize_and_context(
    context_client, context_targets, actors, target_type
):
    client = context_client()
    intent = "task_decomposition" if target_type == "task" else "risk_analysis"
    assert (
        client.post(
            context_url(target_type, context_targets[target_type]),
            {"action": "ai.analyze", "intent": intent},
            format="json",
        ).status_code
        == 200
    )
    ProjectMember.objects.filter(
        project_id=context_targets["project"], user_id=actors["member"]
    ).update(status="REMOVED", left_at=timezone.now())
    for domain in ("project", "team", "progress"):
        response = client.get(context_url(target_type, context_targets[target_type], domain))
        assert response.status_code == 404


@pytest.mark.parametrize("target_type", ["project", "task", "sprint"])
def test_unknown_and_invisible_targets_are_hidden(context_client, context_targets, target_type):
    client = context_client(role="outsider")
    denied = client.get(context_url(target_type, context_targets[target_type], "project"))
    missing = client.get(context_url(target_type, uuid4(), "project"))
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["error"]["code"] == missing.json()["error"]["code"]


@pytest.mark.parametrize("target_type", ["task", "sprint"])
def test_archived_target_cannot_be_read_via_internal_api(
    context_client, context_targets, target_type
):
    model = Task if target_type == "task" else Sprint
    model.objects.filter(pk=context_targets[target_type]).update(archived_at=timezone.now())
    assert (
        context_client()
        .get(context_url(target_type, context_targets[target_type], "project"))
        .status_code
        == 404
    )


def test_teacher_proof_is_fetched_outside_barrier_and_scope_is_current(
    context_client, context_targets, classroom, actors, monkeypatch
):
    calls = []
    original = classroom.teacher_group_ids

    def teacher_groups(self, actor):
        calls.append(connection.in_atomic_block)
        # pytest's outer transaction is expected; the Project barrier must not be held yet.
        assert not any("FOR UPDATE" in query["sql"] for query in connection.queries[-1:])
        return original(self, actor)

    monkeypatch.setattr(classroom, "teacher_group_ids", teacher_groups)
    assert (
        context_client(role="teacher")
        .get(context_url("project", context_targets["project"], "team"))
        .status_code
        == 200
    )
    classroom.teachers[actors["teacher"]] = []
    assert (
        context_client(role="teacher")
        .get(context_url("project", context_targets["project"], "team"))
        .status_code
        == 404
    )
    assert len(calls) == 2

    def fail(self, actor):
        raise WorkError("CLASSROOM_UNAVAILABLE", "Không thể xác minh quyền truy cập lúc này.", 503)

    monkeypatch.setattr(classroom, "teacher_group_ids", fail)
    assert (
        context_client(role="teacher")
        .get(context_url("project", context_targets["project"], "team"))
        .status_code
        == 503
    )
    assert (
        context_client().get(context_url("project", context_targets["project"], "team")).status_code
        == 200
    )


def test_membership_and_deleted_project_are_rechecked_after_acquiring_barrier(
    context_client, context_targets, actors, monkeypatch
):
    import apps.projects.queries.projects as queries

    original = queries.lock_project

    def remove_after_proof(project_id):
        ProjectMember.objects.filter(project_id=project_id, user_id=actors["member"]).update(
            status="REMOVED", left_at=timezone.now()
        )
        return original(project_id)

    monkeypatch.setattr(queries, "lock_project", remove_after_proof)
    assert (
        context_client().get(context_url("project", context_targets["project"], "team")).status_code
        == 404
    )
    Project.objects.filter(pk=context_targets["project"]).update(deleted_at=timezone.now())
    assert (
        context_client(role="leader")
        .get(context_url("project", context_targets["project"], "team"))
        .status_code
        == 404
    )
