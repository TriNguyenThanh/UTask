from uuid import UUID, uuid4

import pytest
from django.utils import timezone

from apps.collaboration.models import Comment
from apps.collaboration.services.comments import comment_command
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task
from common.authentication import Actor
from common.errors import WorkError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_feedback(identity, client_for, actors):
    identity["roles"][str(actors["outsider"])] = ["SYSTEM_ADMIN"]
    return client_for(actors["outsider"])


@pytest.mark.parametrize("subject", ["project", "task"])
def test_admin_comments_only_on_own_without_project_read_or_teacher_event(
    task_api, actors, client_for, admin_feedback, subject
):
    leader, _, create = task_api
    task = create()
    subject_id = task["project_id"] if subject == "project" else task["id"]
    before_receipts = IdempotencyRecord.objects.count()
    response = admin_feedback.post(
        "/comments/",
        {
            f"{subject}_id": subject_id,
            "content_html": "<p>Admin</p><script>alert(1)</script>",
            "mentioned_user_ids": [str(actors["member"])],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="admin-feedback",
    )
    assert response.status_code == 201, response.content
    data = response.json()["data"]
    comment = Comment.objects.get(pk=data["id"])
    assert comment.user_id == actors["outsider"] and not comment.is_teacher_feedback
    assert "script" not in comment.content_html
    assert comment.mentions.get().user_id == actors["member"]
    assert not OutboxEvent.objects.filter(event_type="teacher.feedback.added").exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=comment.pk, event_type="comment.created"
    ).exists()
    for route in [
        f"/projects/{task['project_id']}/",
        f"/tasks/{task['id']}/",
        f"/projects/{task['project_id']}/comments/",
        f"/tasks/{task['id']}/comments/",
        f"/tasks/{task['id']}/activities/",
        f"/tasks/{task['id']}/attachments/",
    ]:
        assert admin_feedback.get(route).status_code == 404
    assert admin_feedback.get("/projects/").json()["data"] == []
    route = f"/comments/{comment.pk}/"
    edited = admin_feedback.patch(route, {"content_html": "Updated"}, format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["data"]["is_teacher_feedback"] is False
    other = leader.post(
        "/comments/", {f"{subject}_id": subject_id, "content_html": "Member"}, format="json"
    )
    other_route = f"/comments/{other.json()['data']['id']}/"
    assert (
        admin_feedback.patch(other_route, {"content_html": "Other"}, format="json").status_code
        == 404
    )
    assert admin_feedback.delete(other_route).status_code == 404
    assert admin_feedback.delete(route).status_code == 200
    comment.refresh_from_db()
    assert comment.deleted_at and Activity.objects.filter(comment=comment).count() == 3
    assert (
        admin_feedback.patch(route, {"content_html": "Deleted"}, format="json").status_code == 404
    )
    assert IdempotencyRecord.objects.count() == before_receipts
    assert Task.objects.get(pk=task["id"]).version == 1
    assert (
        client_for(actors["member"]).get(f"/{subject}s/{subject_id}/comments/").status_code == 200
    )


def test_revoked_admin_and_forged_jwt_role_cannot_replay_or_edit(
    created_project, actors, admin_feedback, identity, token, client_for
):
    body = {"project_id": created_project["id"], "content_html": "Feedback"}
    created = admin_feedback.post("/comments/", body, format="json", HTTP_IDEMPOTENCY_KEY="same")
    assert created.status_code == 201
    route = f"/comments/{created.json()['data']['id']}/"
    identity["roles"][str(actors["outsider"])] = []
    admin_feedback.credentials(
        HTTP_AUTHORIZATION="Bearer " + token(actors["outsider"], roles=["SYSTEM_ADMIN"])
    )
    before = (Comment.objects.count(), Activity.objects.count(), OutboxEvent.objects.count())
    assert (
        admin_feedback.post(
            "/comments/", body, format="json", HTTP_IDEMPOTENCY_KEY="same"
        ).status_code
        == 404
    )
    assert admin_feedback.patch(route, {"content_html": "No"}, format="json").status_code == 404
    assert admin_feedback.delete(route).status_code == 404
    assert before == (
        Comment.objects.count(),
        Activity.objects.count(),
        OutboxEvent.objects.count(),
    )
    identity["roles"][str(actors["outsider"])] = ["SYSTEM_ADMIN"]
    assert (
        admin_feedback.patch(route, {"content_html": "Restored"}, format="json").status_code == 200
    )
    identity["active"] = False
    assert admin_feedback.delete(route).status_code == 401


@pytest.mark.parametrize(
    "field,value",
    [
        ("class_id", None),
        ("classroom_group_id", ""),
        ("archived_at", "now"),
        ("deleted_at", "now"),
    ],
)
def test_admin_feedback_requires_classroom_binding_and_live_project(
    created_project, admin_feedback, field, value
):
    source = Project.objects.get(pk=created_project["id"])
    attributes = {
        "class_id": source.class_id,
        "classroom_group_id": source.classroom_group_id,
        field: timezone.now() if value == "now" else value,
    }
    project = Project.objects.create(
        identifier="ADBOUND", name="Admin feedback boundary", **attributes
    )
    response = admin_feedback.post(
        "/comments/", {"project_id": str(project.pk), "content_html": "No"}, format="json"
    )
    assert response.status_code == (400 if field == "archived_at" else 404)
    assert not Comment.objects.exists()


@pytest.mark.parametrize("field", ["archived_at", "deleted_at"])
def test_admin_feedback_preserves_task_lifecycle_guards(task_api, admin_feedback, field):
    _, _, create = task_api
    task = create()
    Task.objects.filter(pk=task["id"]).update(**{field: timezone.now()})
    response = admin_feedback.post(
        "/comments/", {"task_id": task["id"], "content_html": "No"}, format="json"
    )
    assert response.status_code == (400 if field == "archived_at" else 404)
    assert not Comment.objects.exists()


def test_admin_feedback_keeps_mentions_and_project_task_writes_scoped(
    task_api, admin_feedback, project_payload, monkeypatch, classroom
):
    _, _, create = task_api
    task = create()
    monkeypatch.setattr(
        classroom,
        "teacher_mention_ids",
        staticmethod(lambda group, ids, actor: set()),
        raising=False,
    )
    response = admin_feedback.post(
        "/comments/",
        {
            "task_id": task["id"],
            "content_html": "No",
            "mentioned_user_ids": [str(uuid4())],
        },
        format="json",
    )
    assert response.status_code == 422
    assert not Comment.objects.exists()
    assert (
        admin_feedback.post(
            "/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="admin-create"
        ).status_code
        == 403
    )
    assert (
        admin_feedback.patch(
            f"/projects/{task['project_id']}/", {"name": "No", "expected_version": 1}, format="json"
        ).status_code
        == 404
    )
    assert (
        admin_feedback.patch(
            f"/tasks/{task['id']}/", {"title": "No", "expected_version": 1}, format="json"
        ).status_code
        == 404
    )


def test_admin_command_rechecks_current_role_after_view_authorization(
    created_project, actors, token, monkeypatch
):
    from rest_framework.exceptions import NotFound

    actor = Actor(actors["outsider"], access_token=token(actors["outsider"]))
    monkeypatch.setattr(
        "infrastructure.identity.IdentityClient.current_user",
        lambda self, token: {"id": str(actor.id), "roles": []},
    )
    with pytest.raises(NotFound):
        comment_command(actor, UUID(created_project["id"]), {"content_html": "No"})
    assert not Comment.objects.exists()


def test_admin_command_cannot_move_comment_between_project_and_task(
    task_api, admin_feedback, actors, token
):
    from rest_framework.exceptions import NotFound

    _, _, create = task_api
    task = create()
    response = admin_feedback.post(
        "/comments/", {"project_id": task["project_id"], "content_html": "Original"}, format="json"
    )
    comment = Comment.objects.get(pk=response.json()["data"]["id"])
    actor = Actor(actors["outsider"], access_token=token(actors["outsider"]))
    with pytest.raises(NotFound):
        comment_command(
            actor,
            UUID(task["project_id"]),
            {"content_html": "Moved"},
            task_id=UUID(task["id"]),
            comment_id=comment.pk,
        )
    with pytest.raises((NotFound, WorkError)):
        comment_command(
            actor, UUID(task["project_id"]), {}, task_id=uuid4(), comment_id=comment.pk, delete=True
        )
    comment.refresh_from_db()
    assert comment.content_stripped == "Original" and comment.task_id is None
