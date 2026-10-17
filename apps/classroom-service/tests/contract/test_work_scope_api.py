from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import ClassTeacher
from apps.groups.models import GroupProjectLink

pytestmark = [pytest.mark.django_db, pytest.mark.contract]
WORK_CALLER = {"HTTP_X_SERVICE_KEY": "test-work-caller-key"}


def test_group_snapshot_requires_work_caller_and_current_relationship(group, client_for, actors):
    leader = client_for(actors["leader"])
    path = f"/internal/groups/{group.pk}/snapshot/"

    assert leader.get(path).status_code == 403
    response = leader.get(path, **WORK_CALLER)
    assert response.status_code == 200
    snapshot = response.json()["data"]
    assert snapshot["group_id"] == str(group.pk)
    assert snapshot["class_id"] == str(group.class_section_id)
    assert snapshot["source_version"] == group.source_version
    assert {row["user_id"] for row in snapshot["members"]} == {
        str(actors["leader"]),
        str(actors["member"]),
    }
    assert client_for(uuid4()).get(path, **WORK_CALLER).status_code == 404


def test_recovery_snapshot_requires_service_key_without_user_bearer(group):
    path = f"/internal/groups/{group.pk}/recovery-snapshot/"

    assert APIClient().get(path, **WORK_CALLER).status_code == 200
    assert APIClient().get(path).status_code == 403
    assert APIClient().get(path, HTTP_X_SERVICE_KEY="wrong-key").status_code == 403


def test_teacher_group_scope_removes_revoked_assignment(group, client_for, actors):
    teacher = client_for(actors["teacher"])
    path = "/internal/teachers/groups/"
    assert str(group.pk) in teacher.get(path, **WORK_CALLER).json()["data"]["group_ids"]
    ClassTeacher.objects.filter(class_section=group.class_section).update(
        status="LEFT", left_at=timezone.now()
    )

    response = teacher.get(path, **WORK_CALLER)

    assert response.status_code == 200
    assert response.json()["data"]["group_ids"] == []


def test_feedback_scope_binds_actor_project_group_version_and_mentions(group, client_for, actors):
    project_id = uuid4()
    GroupProjectLink.objects.create(
        group=group, class_section=group.class_section, project_id=project_id
    )
    response = client_for(actors["teacher"]).post(
        f"/internal/groups/{group.pk}/feedback-scope/",
        {"project_id": str(project_id)},
        format="json",
        **WORK_CALLER,
    )

    assert response.status_code == 200, response.content
    scope = response.json()["data"]
    assert scope["actor_id"] == str(actors["teacher"])
    assert scope["project_id"] == str(project_id)
    assert scope["group_id"] == str(group.pk)
    assert scope["source_version"] == group.source_version
    assert timezone.now() < timezone.datetime.fromisoformat(
        scope["expires_at"].replace("Z", "+00:00")
    )
    assert set(scope["mentionable_user_ids"]) == {
        str(actors["teacher"]),
        str(actors["leader"]),
        str(actors["member"]),
    }


@pytest.mark.parametrize("actor", ["teacher", "leader"])
def test_feedback_scope_rejects_unlinked_project_or_non_teacher(group, client_for, actors, actor):
    response = client_for(actors[actor]).post(
        f"/internal/groups/{group.pk}/feedback-scope/",
        {"project_id": str(uuid4())},
        format="json",
        **WORK_CALLER,
    )

    assert response.status_code == (404 if actor == "teacher" else 403)


def test_member_mention_scope_returns_only_active_class_teachers(group, client_for, actors):
    response = client_for(actors["member"]).get(
        f"/internal/groups/{group.pk}/mention-scope/", **WORK_CALLER
    )

    assert response.status_code == 200
    assert response.json()["data"]["mentionable_user_ids"] == [str(actors["teacher"])]
