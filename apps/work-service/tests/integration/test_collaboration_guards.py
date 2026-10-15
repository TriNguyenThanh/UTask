from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.collaboration.models import Attachment, Comment, CommentMention
from apps.collaboration.tasks import cleanup_attachments
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task
from common.errors import WorkError
from infrastructure.storage import ObjectFacts
from tests.fixtures.collaboration import pending
from tests.fixtures.storage import storage as storage

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_foreign_epic_label_and_metadata_routes_are_rejected(task_api, foreign_scope):
    leader, _, create = task_api
    project, _ = foreign_scope
    task = create()
    root = f"/projects/{project['id']}/"
    label = leader.post(
        root + "labels/", {"name": "Foreign label", "color": "#123456"}, format="json"
    ).json()["data"]
    epic = leader.post(root + "epics/", {"name": "Foreign epic"}, format="json").json()["data"]
    before = OutboxEvent.objects.count()
    reply = leader.patch(
        f"/tasks/{task['id']}/",
        {"expected_version": 1, "epic_id": epic["id"]},
        format="json",
    )
    assert reply.status_code == 422
    reply = leader.post(
        f"/tasks/{task['id']}/labels/",
        {"expected_version": 1, "action": "ADD", "label_ids": [label["id"]]},
        format="json",
    )
    assert reply.status_code == 422
    for kind, row in [("labels", label), ("epics", epic)]:
        reply = leader.patch(
            f"/projects/{task['project_id']}/{kind}/{row['id']}/",
            {"name": "Wrong scope"},
            format="json",
        )
        assert reply.status_code == 404
    assert Task.objects.get(pk=task["id"]).version == 1
    assert OutboxEvent.objects.count() == before


def test_wrong_class_feedback_author_scope_loss_and_sanitized_mentions(
    task_api, actors, client_for, classroom
):
    leader, _, create = task_api
    task = create()
    teacher = client_for(actors["teacher"])
    classroom.teachers[actors["teacher"]] = ["other-group"]
    body = {"task_id": task["id"], "content_html": "Wrong class"}
    assert teacher.post("/comments/", body, format="json").status_code == 404
    assert not Comment.objects.exists()
    member = client_for(actors["member"])
    safe = (
        f'<script><mention-component data-id="{actors["outsider"]}">'
        'Fake</mention-component></script><p onclick="evil()">Safe</p>'
    )
    reply = member.post("/comments/", {"task_id": task["id"], "content_html": safe}, format="json")
    assert reply.status_code == 201, reply.content
    data = reply.json()["data"]
    assert data["content_html"] == "<p>Safe</p>" and data["mentioned_user_ids"] == []
    assert not CommentMention.objects.exists()
    project = Project.objects.get(pk=task["project_id"])
    project.members.filter(user_id=actors["member"]).update(status="LEFT", left_at=timezone.now())
    before = OutboxEvent.objects.count()
    for method in ["patch", "delete"]:
        call = getattr(member, method)
        reply = call(
            f"/comments/{data['id']}/",
            {"content_html": "Revoked"} if method == "patch" else {},
            format="json",
        )
        assert reply.status_code == 404, reply.content
    assert Comment.objects.get(pk=data["id"]).deleted_at is None
    assert Task.objects.get(pk=task["id"]).version == 1
    assert OutboxEvent.objects.count() == before


@pytest.mark.parametrize(
    "facts", [ObjectFacts(11, "text/plain", True), ObjectFacts(10, "application/pdf", True)]
)
def test_attachment_metadata_mismatch_does_not_confirm(task_api, storage, facts):
    leader, _, create = task_api
    task = create()
    route = f"/tasks/{task['id']}/attachments/"
    row = pending(leader, route)
    storage.objects[row.storage_key] = facts
    before = OutboxEvent.objects.count()
    reply = leader.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="bad-metadata"
    )
    assert reply.status_code == 422, reply.content
    row.refresh_from_db()
    assert row.status == "PENDING" and row.confirmed_at is None
    assert not IdempotencyRecord.objects.filter(idempotency_key="bad-metadata").exists()
    assert OutboxEvent.objects.count() == before


@pytest.mark.django_db(transaction=True)
def test_attachment_expiry_after_inspect_is_rechecked_under_lock(task_api, storage, monkeypatch):
    leader, _, create = task_api
    task = create()
    route = f"/tasks/{task['id']}/attachments/"
    row = pending(leader, route)
    clock = {"now": timezone.now()}
    monkeypatch.setattr("django.utils.timezone.now", lambda: clock["now"])

    def inspect(self, attachment):
        assert not connection.in_atomic_block
        clock["now"] = attachment.expires_at + timedelta(seconds=1)
        return ObjectFacts(attachment.file_size, attachment.content_type, True)

    monkeypatch.setattr(storage, "inspect", inspect)
    reply = leader.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="expiry-race"
    )
    assert reply.status_code == 400, reply.content
    row.refresh_from_db()
    assert row.status == "PENDING" and row.confirmed_at is None
    assert not IdempotencyRecord.objects.filter(idempotency_key="expiry-race").exists()
    assert not OutboxEvent.objects.filter(event_type="attachment.confirmed").exists()


@pytest.mark.django_db(transaction=True)
def test_cleanup_storage_failure_commits_expiry_and_retries_without_duplicate_event(
    task_api, storage, monkeypatch
):
    leader, _, create = task_api
    task = create()
    route = f"/tasks/{task['id']}/attachments/"
    row = pending(leader, route)
    future = row.expires_at + timedelta(seconds=1)
    monkeypatch.setattr("django.utils.timezone.now", lambda: future)
    delete = storage.delete

    def unavailable(self, key):
        assert not connection.in_atomic_block
        raise WorkError("STORAGE_UNAVAILABLE", "Storage offline", 503)

    monkeypatch.setattr(storage, "delete", unavailable)
    with pytest.raises(WorkError):
        cleanup_attachments()
    row.refresh_from_db()
    assert row.status == "EXPIRED"
    event = OutboxEvent.objects.get(event_type="attachment.expired")
    assert Activity.objects.filter(task_id=task["id"], verb="expired").count() == 1
    monkeypatch.setattr(storage, "delete", delete)
    assert cleanup_attachments() == 1
    assert storage.deletes == [row.storage_key]
    assert OutboxEvent.objects.get(event_type="attachment.expired").pk == event.pk


def test_confirm_rejects_forged_owner_key_and_wrong_download_scope(
    task_api, storage, client_for, actors
):
    leader, _, create = task_api
    task = create()
    route = f"/tasks/{task['id']}/attachments/"
    row = pending(leader, route)
    reply = leader.post(
        route,
        {
            "attachment_id": str(row.pk),
            "uploaded_by_user_id": str(actors["member"]),
            "storage_key": "work/forged",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="forged",
    )
    assert reply.status_code == 400
    reply = leader.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="confirm"
    )
    assert reply.status_code == 200, reply.content
    assert client_for(actors["outsider"]).get(route + str(row.pk) + "/download/").status_code == 404
    assert client_for(actors["member"]).delete(route + str(row.pk) + "/").status_code == 403
    assert Attachment.objects.get(pk=row.pk).deleted_at is None
