import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.collaboration.models import Attachment, Comment
from apps.collaboration.tasks import cleanup_attachments
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Epic, Label, Task
from apps.tasks.tasks import scan_deadlines
from infrastructure.storage import ObjectFacts
from tests.fixtures.storage import storage as storage

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_label_epic_permissions_filter_and_tombstones(task_api, client_for, actors):
    leader, task_route, create = task_api
    project_id = task_route.split("/")[4]
    member = client_for(actors["member"])
    labels = f"/projects/{project_id}/labels/"
    label = member.post(labels, {"name": "Backend", "color": "#123456"}, format="json").json()[
        "data"
    ]
    assert member.get(labels).json()["data"] == [label]
    before_revision = Project.objects.get(pk=project_id).board_revision
    changed = member.patch(
        labels + label["id"] + "/",
        {"color": "#abcdef", "description": "Đã kiểm API"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    label = changed.json()["data"]
    persisted = Label.objects.get(pk=label["id"])
    assert persisted.color == label["color"] == "#abcdef"
    assert persisted.description == label["description"] == "Đã kiểm API"
    assert Project.objects.get(pk=project_id).board_revision == before_revision + 1
    changes = Activity.objects.filter(label_id=label["id"], verb="updated")
    assert changes.count() == 2
    assert json.loads(changes.get(field="color").old_value) == "#123456"
    assert json.loads(changes.get(field="color").new_value) == "#abcdef"
    event = OutboxEvent.objects.get(event_type="label.updated")
    assert event.aggregate_id == label["id"] and event.data["data"] == label
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(labels)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [label]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    assert client_for(actors["outsider"]).get(labels).status_code == 404
    assert (
        leader.post(labels, {"name": "Backend", "color": "#123456"}, format="json").status_code
        == 409
    )
    task = create()
    task_url = f"/tasks/{task['id']}/"
    response = member.post(
        task_url + "labels/",
        {"expected_version": 1, "action": "ADD", "label_ids": [label["id"]]},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["data"]["label_ids"] == [label["id"]]
    assert (
        leader.get(task_route, {"label_id": label["id"]}).json()["meta"]["pagination"][
            "total_count"
        ]
        == 1
    )
    assert member.delete(labels + label["id"] + "/").status_code == 403
    assert leader.delete(labels + label["id"] + "/").status_code == 200
    assert Label.objects.get(pk=label["id"]).deleted_at is not None
    assert member.get(labels).json()["data"] == []
    assert member.get(labels).json()["meta"]["pagination"]["total_count"] == 0
    assert leader.get(task_route, {"label_id": label["id"]}).json()["data"] == []
    epics = f"/projects/{project_id}/epics/"
    epic = leader.post(
        epics, {"name": "Auth", "lead_user_id": str(actors["member"])}, format="json"
    ).json()["data"]
    updated = member.patch(epics + epic["id"] + "/", {"status": "IN_PROGRESS"}, format="json")
    assert updated.status_code == 200, updated.content
    epic = updated.json()["data"]
    persisted = Epic.objects.get(pk=epic["id"])
    assert persisted.status == epic["status"] == "IN_PROGRESS"
    assert persisted.lead_user_id == actors["member"]
    assert OutboxEvent.objects.get(event_type="epic.updated").data["data"] == epic
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(epics)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [epic]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    assert client_for(actors["outsider"]).get(epics).status_code == 404
    assert (
        member.patch(
            epics + epic["id"] + "/", {"target_date": "2027-01-01"}, format="json"
        ).status_code
        == 403
    )
    unrelated = create(assignee_ids=[], epic_id=epic["id"])
    assert (
        member.patch(
            f"/tasks/{unrelated['id']}/",
            {"expected_version": 1, "description_html": "Forbidden"},
            format="json",
        ).status_code
        == 403
    )
    assert leader.delete(epics + epic["id"] + "/").status_code == 200
    assert Epic.objects.get(pk=epic["id"]).deleted_at is not None
    assert member.get(epics).json()["data"] == []
    assert Task.objects.get(pk=unrelated["id"]).epic_id == UUID(epic["id"])
    assert (
        leader.patch(
            f"/tasks/{unrelated['id']}/",
            {"expected_version": 1, "title": "History preserved"},
            format="json",
        ).status_code
        == 200
    )


def test_teacher_feedback_mentions_diff_scope_and_timeline(
    task_api, client_for, actors, monkeypatch, classroom
):
    leader, _, create = task_api
    task = create()
    teacher = client_for(actors["teacher"])
    project = Project.objects.get(pk=task["project_id"])
    teacher_id = actors["teacher"]

    def recipients(group, ids, actor):
        assert group == project.classroom_group_id
        return {teacher_id} & ids

    monkeypatch.setattr(classroom, "teacher_mention_ids", staticmethod(recipients), raising=False)
    body = {
        "task_id": task["id"],
        "content_html": (
            '<p>Hello <mention-component entity_name="user_mention" '
            f'entity_identifier="{actors["member"]}">Bạn</mention-component></p>'
        ),
    }
    response = teacher.post("/comments/", body, format="json")
    assert response.status_code == 201, response.content
    comment = response.json()["data"]
    assert comment["is_teacher_feedback"] is True
    assert Task.objects.get(pk=task["id"]).version == 1
    assert Comment.objects.get(pk=comment["id"]).project_id is None
    route = f"/comments/{comment['id']}/"
    assert leader.patch(route, {"content_html": "Other author"}, format="json").status_code == 403
    assert (
        teacher.patch(route, {"content_html": body["content_html"]}, format="json").status_code
        == 200
    )
    assert OutboxEvent.objects.filter(event_type="comment.mentions.added").count() == 1
    response = teacher.patch(
        route,
        {"content_html": "<p>Mới</p>", "mentioned_user_ids": [str(actors["leader"])]},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert OutboxEvent.objects.filter(event_type="comment.mentions.added").count() == 2
    assert (
        teacher.patch(
            route,
            {"content_html": "Fake", "mentioned_user_ids": [str(actors["outsider"])]},
            format="json",
        ).status_code
        == 422
    )
    member = client_for(actors["member"])
    project_reply = member.post(
        "/comments/",
        {
            "project_id": task["project_id"],
            "content_html": "Mention teacher",
            "mentioned_user_ids": [str(teacher_id)],
        },
        format="json",
    )
    assert project_reply.status_code == 201, project_reply.content
    project_comment = project_reply.json()["data"]
    project_row = Comment.objects.get(pk=project_comment["id"])
    assert project_row.project_id == project.pk and project_row.task_id is None
    assert project_row.is_teacher_feedback is False
    assert project_row.mentions.get().user_id == teacher_id
    project_route = f"/projects/{project.pk}/comments/"
    receipt_count = IdempotencyRecord.objects.count()
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(project_route)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [project_comment]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    # Task comments use a different XOR subject and cannot enter the Project list.
    assert comment["id"] not in [row["id"] for row in listed.json()["data"]]
    assert client_for(actors["outsider"]).get(project_route).status_code == 404
    project_comment_route = f"/comments/{project_comment['id']}/"
    edited = member.patch(project_comment_route, {"content_html": "<p>Đã sửa</p>"}, format="json")
    assert edited.status_code == 200, edited.content
    project_row.refresh_from_db()
    assert project_row.content_stripped == "Đã sửa" and not project_row.mentions.exists()
    assert member.get(project_route).json()["data"] == [edited.json()["data"]]
    assert member.delete(project_comment_route).status_code == 200
    project_row.refresh_from_db()
    assert project_row.deleted_at is not None and leader.get(project_route).json()["data"] == []
    assert Activity.objects.filter(comment=project_row).count() == 3
    assert (
        OutboxEvent.objects.filter(aggregate_id=str(project_row.pk), event_type="comment.updated")
        .get()
        .data["data"]["content_stripped"]
        == "Đã sửa"
    )
    assert IdempotencyRecord.objects.count() == receipt_count
    assert Task.objects.get(pk=task["id"]).version == 1
    assert (
        teacher.post(
            "/comments/", {**body, "project_id": task["project_id"]}, format="json"
        ).status_code
        == 400
    )
    assert client_for(actors["outsider"]).get(f"/tasks/{task['id']}/comments/").status_code == 404
    assert leader.delete(route).status_code == 200
    assert leader.get(f"/tasks/{task['id']}/comments/").json()["data"] == []
    timeline = leader.get(f"/tasks/{task['id']}/activities/").json()["data"]
    assert any(row["verb"] == "deleted" for row in timeline)
    assert Task.objects.get(pk=task["id"]).version == 1


def test_deadline_retry_change_and_terminal_exclusion(task_api, monkeypatch):
    leader, _, create = task_api
    monkeypatch.setattr(
        "django.utils.timezone.now", lambda: datetime(2026, 10, 9, 17, 30, tzinfo=UTC)
    )
    day = date(2026, 10, 10)
    task = create(due_date=day.isoformat())
    assert scan_deadlines() == 1
    assert scan_deadlines() == 0
    reply = leader.patch(
        f"/tasks/{task['id']}/",
        {"expected_version": 1, "due_date": (day + timedelta(days=1)).isoformat()},
        format="json",
    )
    assert reply.status_code == 200
    assert scan_deadlines() == 1
    assert scan_deadlines() == 0
    # Equal timestamps and a return to the original date still create a new deadline revision.
    assert (
        leader.patch(
            f"/tasks/{task['id']}/",
            {"expected_version": 2, "due_date": day.isoformat()},
            format="json",
        ).status_code
        == 200
    )
    assert scan_deadlines() == 1
    assert (
        leader.patch(
            f"/tasks/{task['id']}/",
            {"expected_version": 3, "description_html": "Content only"},
            format="json",
        ).status_code
        == 200
    )
    assert scan_deadlines() == 0
    row = Task.objects.get(pk=task["id"])
    done = row.project.states.get(group="COMPLETED")
    assert (
        leader.patch(
            f"/tasks/{row.pk}/transition/",
            {"expected_version": 4, "target_state_id": str(done.pk)},
            format="json",
        ).status_code
        == 200
    )
    assert scan_deadlines() == 0
    cancelled_state = leader.post(
        f"/projects/{task['project_id']}/states/",
        {"name": "Cancelled", "color": "#123456", "sequence": 60000, "group": "CANCELLED"},
        format="json",
    )
    assert cancelled_state.status_code == 201, cancelled_state.content
    cancelled = create(due_date=day.isoformat())
    assert (
        leader.patch(
            f"/tasks/{cancelled['id']}/transition/",
            {"expected_version": 1, "target_state_id": cancelled_state.json()["data"]["id"]},
            format="json",
        ).status_code
        == 200
    )
    assert Task.objects.get(pk=cancelled["id"]).completed_at is None
    archived, deleted = create(due_date=day.isoformat()), create(due_date=day.isoformat())
    assert (
        leader.post(
            f"/tasks/{archived['id']}/archive/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert (
        leader.delete(
            f"/tasks/{deleted['id']}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert scan_deadlines() == 0
    assert OutboxEvent.objects.filter(event_type="task.deadline.reminder").count() == 3


def test_attachment_subject_owner_content_confirm_replay_download_and_cleanup(
    task_api, client_for, actors, storage, monkeypatch
):
    leader, _, create = task_api
    task = create()
    member = client_for(actors["member"])
    route = f"/tasks/{task['id']}/attachments/"
    response = member.post(
        route + "presigned-url/",
        {"file_name": "../notes.txt", "file_size": 10, "content_type": "text/plain"},
        format="json",
    )
    assert response.status_code == 200, response.content
    attachment_id = response.json()["data"]["attachment_id"]
    row = Attachment.objects.get(pk=attachment_id)
    assert row.file_name == "notes.txt"
    assert row.project_id is None
    assert leader.get(route).json()["data"] == []
    assert (
        leader.post(
            route, {"attachment_id": attachment_id}, format="json", HTTP_IDEMPOTENCY_KEY="owner"
        ).status_code
        == 403
    )
    storage.objects[row.storage_key] = ObjectFacts(10, "text/plain", False)
    assert (
        member.post(
            route, {"attachment_id": attachment_id}, format="json", HTTP_IDEMPOTENCY_KEY="confirm"
        ).status_code
        == 422
    )
    storage.objects[row.storage_key] = ObjectFacts(10, "text/plain", True)
    response = member.post(
        route, {"attachment_id": attachment_id}, format="json", HTTP_IDEMPOTENCY_KEY="confirm"
    )
    assert response.status_code == 200, response.content
    assert (
        member.post(
            route, {"attachment_id": attachment_id}, format="json", HTTP_IDEMPOTENCY_KEY="confirm"
        ).json()
        == response.json()
    )
    assert OutboxEvent.objects.filter(event_type="attachment.confirmed").count() == 1
    assert Attachment.objects.count() == 1
    teacher = client_for(actors["teacher"])
    assert teacher.get(route + attachment_id + "/download/").status_code == 200
    assert (
        teacher.post(
            route + "presigned-url/",
            {"file_name": "x", "file_size": 1, "content_type": "text/plain"},
            format="json",
        ).status_code
        == 403
    )
    project_route = f"/projects/{task['project_id']}/attachments/"
    assert (
        member.post(
            project_route,
            {"attachment_id": attachment_id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="wrong-subject",
        ).status_code
        == 404
    )
    assert leader.get(f"/tasks/{task['id']}/").json()["data"]["attachments_count"] == 1
    assert member.delete(route + attachment_id + "/").status_code == 200
    assert leader.get(route).json()["data"] == []
    assert cleanup_attachments() == 1
    assert storage.deletes == [row.storage_key]
    response = member.post(
        project_route + "presigned-url/",
        {"file_name": "x", "file_size": 1, "content_type": "application/pdf"},
        format="json",
    )
    pending = Attachment.objects.get(pk=response.json()["data"]["attachment_id"])
    future = timezone.now() + timedelta(minutes=16)
    monkeypatch.setattr("django.utils.timezone.now", lambda: future)
    assert cleanup_attachments() == 2
    pending.refresh_from_db()
    assert pending.status == "EXPIRED"
    assert (
        member.post(
            project_route,
            {"attachment_id": str(pending.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="expired",
        ).status_code
        == 400
    )


def test_collaboration_database_subject_identity(task_api):
    _, _, create = task_api
    task = create()
    comment = Comment.objects.create(
        task_id=task["id"],
        user_id=task["created_by_user_id"],
        content_html="x",
        content_stripped="x",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.filter(pk=comment.pk).update(user_id=task["assignee_ids"][0])
    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.create(
            task_id=task["id"],
            project_id=task["project_id"],
            user_id=task["created_by_user_id"],
            content_html="x",
            content_stripped="x",
        )


def test_feedback_proof_expiry_and_presign_failure_leave_correct_state(
    task_api, client_for, actors, storage, monkeypatch, classroom
):
    from common.errors import WorkError
    from infrastructure.collaboration_scope import VerifiedFeedbackScope

    leader, _, create = task_api
    task = create()
    project = Project.objects.get(pk=task["project_id"])
    expired = VerifiedFeedbackScope(
        actors["teacher"],
        project.pk,
        project.classroom_group_id,
        1,
        timezone.now() - timedelta(seconds=1),
    )
    monkeypatch.setattr(
        classroom, "teacher_feedback_scope", staticmethod(lambda project, actor: expired)
    )
    response = client_for(actors["teacher"]).post(
        "/comments/", {"task_id": task["id"], "content_html": "Stale proof"}, format="json"
    )
    assert response.status_code == 503
    assert not Comment.objects.exists()

    def fail(self, row):
        raise WorkError("STORAGE_UNAVAILABLE", "Signer unavailable", 503)

    monkeypatch.setattr(storage, "presign", fail)
    response = leader.post(
        f"/tasks/{task['id']}/attachments/presigned-url/",
        {"file_name": "x.txt", "file_size": 1, "content_type": "text/plain"},
        format="json",
    )
    assert response.status_code == 503
    assert Attachment.objects.get().status == "PENDING"
    assert not OutboxEvent.objects.filter(event_type="attachment.confirmed").exists()
