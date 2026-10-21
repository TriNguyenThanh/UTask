import json

import pytest
from django.db import connection
from django.utils import timezone

from apps.collaboration.models import Attachment, Comment, CommentMention
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Epic, Label, Task
from tests.event_contracts import assert_event_contract
from tests.fixtures.project_api import foreign_scope as foreign_scope
from tests.fixtures.storage import storage as storage
from tests.fixtures.transactions import effect_state
from tests.fixtures.transactions import reject_outbox_event as reject_outbox_event

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.mark.django_db(transaction=True)
def test_project_file_confirm_read_download_delete_and_retry(
    project_upload, actors, client_for, storage, monkeypatch
):
    uploader, route, row = project_upload
    before = effect_state(row.project_id)
    initial = uploader.get(route).json()
    assert initial["data"] == [] and initial["meta"]["pagination"]["total_count"] == 0
    calls = {"inspect": 0, "download": []}
    original_inspect = storage.inspect

    def inspect(adapter, attachment):
        assert not connection.in_atomic_block
        calls["inspect"] += 1
        return original_inspect(adapter, attachment)

    def download(adapter, attachment):
        assert not connection.in_atomic_block
        calls["download"].append(attachment.pk)
        return "https://storage.test/get/" + str(attachment.pk)

    monkeypatch.setattr(storage, "inspect", inspect)
    monkeypatch.setattr(storage, "download", download)
    body = {"attachment_id": str(row.pk)}
    confirmed = uploader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="project-confirm")
    assert confirmed.status_code == 200, confirmed.content
    data = confirmed.json()["data"]
    row.refresh_from_db()
    assert row.status == data["status"] == "CONFIRMED"
    assert row.confirmed_at.isoformat().replace("+00:00", "Z") == data["confirmed_at"]
    assert data["project_id"] == str(row.project_id) and data["task_id"] is None
    assert data["uploaded_by_user_id"] == str(actors["member"])
    assert data["file_size"] == row.file_size == 10
    assert "storage_key" not in data and "presigned_url" not in data
    activity = Activity.objects.get(project_id=row.project_id, field="attachment", verb="created")
    assert activity.actor_user_id == actors["member"] and json.loads(activity.new_value) == data
    event = OutboxEvent.objects.get(event_type="attachment.confirmed")
    assert event.aggregate_type == "project" and event.aggregate_id == str(row.project_id)
    assert event.data["data"] == data
    receipt = IdempotencyRecord.objects.get(idempotency_key="project-confirm")
    assert receipt.user_id == actors["member"] and receipt.endpoint_path == route
    assert receipt.response_body == confirmed.json() and receipt.response_status == 200
    assert (
        Project.objects.get(pk=row.project_id).board_revision
        == before["project"]["board_revision"] + 1
    )
    committed = effect_state(row.project_id)
    # Retry after a lost response must neither inspect storage again nor write another effect.
    replay = uploader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="project-confirm")
    assert replay.status_code == 200 and replay.json() == confirmed.json()
    assert calls["inspect"] == 1 and effect_state(row.project_id) == committed
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(route)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [data]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    teacher = client_for(actors["teacher"])
    downloaded = teacher.get(route + str(row.pk) + "/download/")
    assert downloaded.status_code == 200, downloaded.content
    assert downloaded.json()["data"] == {
        "download_url": "https://storage.test/get/" + str(row.pk),
        "expires_in": 300,
    }
    assert calls["download"] == [row.pk] and effect_state(row.project_id) == committed
    removed = uploader.delete(route + str(row.pk) + "/")
    assert removed.status_code == 200, removed.content
    row.refresh_from_db()
    assert row.deleted_at is not None and removed.json()["data"]["deleted_at"] is not None
    assert row.status == "CONFIRMED" and row.confirmed_at is not None
    deleted = OutboxEvent.objects.get(event_type="attachment.deleted")
    assert deleted.aggregate_type == "project" and deleted.data["data"] == removed.json()["data"]
    activity = Activity.objects.get(project_id=row.project_id, field="attachment", verb="deleted")
    assert json.loads(activity.old_value) == removed.json()["data"]
    assert uploader.get(route).json()["data"] == []
    assert uploader.get(route).json()["meta"]["pagination"]["total_count"] == 0
    after_delete = effect_state(row.project_id)
    assert teacher.get(route + str(row.pk) + "/download/").status_code == 404
    assert uploader.delete(route + str(row.pk) + "/").status_code == 404
    assert effect_state(row.project_id) == after_delete
    assert calls["download"] == [row.pk]
    assert IdempotencyRecord.objects.filter(endpoint_path=route).count() == 1


@pytest.mark.parametrize("actor", ["teacher", "outsider"])
def test_project_file_write_permissions_and_read_scope(project_upload, actors, client_for, actor):
    uploader, route, row = project_upload
    confirmed = uploader.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="confirm-scope"
    )
    assert confirmed.status_code == 200, confirmed.content
    before = effect_state(row.project_id)
    client = client_for(actors[actor])
    expected = 403 if actor == "teacher" else 404
    presign = client.post(
        route + "presigned-url/",
        {"file_name": "x.txt", "file_size": 1, "content_type": "text/plain"},
        format="json",
    )
    confirm = client.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="denied"
    )
    removed = client.delete(route + str(row.pk) + "/")
    for response in [presign, confirm, removed]:
        assert response.status_code == expected, response.content
        assert response.json()["success"] is False
    if actor == "outsider":
        assert client.get(route).status_code == 404
        assert client.get(route + str(row.pk) + "/download/").status_code == 404
    assert Attachment.objects.count() == 1
    row.refresh_from_db()
    assert row.status == "CONFIRMED" and row.deleted_at is None
    assert effect_state(row.project_id) == before


def test_project_file_wrong_subject_pending_download_and_receipt_conflict(
    project_upload, task_api, foreign_scope, client_for, actors
):
    uploader, route, row = project_upload
    leader, _, create = task_api
    task = create()
    other, _ = foreign_scope
    body = {"attachment_id": str(row.pk)}
    before = effect_state(row.project_id)
    for wrong_route in [
        f"/tasks/{task['id']}/attachments/",
        f"/projects/{other['id']}/attachments/",
    ]:
        client = uploader if "/tasks/" in wrong_route else leader
        assert (
            client.post(
                wrong_route, body, format="json", HTTP_IDEMPOTENCY_KEY="wrong-subject"
            ).status_code
            == 404
        )
        assert client.get(wrong_route + str(row.pk) + "/download/").status_code == 404
        assert client.delete(wrong_route + str(row.pk) + "/").status_code == 404
    assert uploader.get(route + str(row.pk) + "/download/").status_code == 400
    assert effect_state(row.project_id) == before
    first = uploader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="shared-key")
    assert first.status_code == 200, first.content
    another = uploader.post(
        route + "presigned-url/",
        {"file_name": "another.txt", "file_size": 2, "content_type": "text/plain"},
        format="json",
    ).json()["data"]["attachment_id"]
    before = effect_state(row.project_id)
    conflict = uploader.post(
        route, {"attachment_id": another}, format="json", HTTP_IDEMPOTENCY_KEY="shared-key"
    )
    assert conflict.status_code == 422, conflict.content
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
    assert Attachment.objects.get(pk=another).status == "PENDING"
    assert effect_state(row.project_id) == before
    # A new key can recover the existing confirmed allocation without repeating the effect.
    repeated = uploader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="new-key")
    assert repeated.status_code == 200 and repeated.json()["data"] == first.json()["data"]
    assert OutboxEvent.objects.filter(event_type="attachment.confirmed").count() == 1
    assert (
        Activity.objects.filter(
            project_id=row.project_id, field="attachment", verb="created"
        ).count()
        == 1
    )
    assert IdempotencyRecord.objects.filter(endpoint_path=route).count() == 2
    assert client_for(actors["leader"]).delete(route + str(row.pk) + "/").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"file_size": 0},
        {"file_size": 26214401},
        {"content_type": "text/html"},
        {"file_name": "\n"},
        {"storage_key": "work/forged"},
        {"uploaded_by_user_id": "forged"},
    ],
)
def test_project_presign_validation_has_no_allocation(created_project, client_for, actors, payload):
    client = client_for(actors["member"])
    before = effect_state(created_project["id"])
    response = client.post(
        f"/projects/{created_project['id']}/attachments/presigned-url/",
        {"file_name": "x.txt", "file_size": 1, "content_type": "text/plain", **payload},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not Attachment.objects.exists() and effect_state(created_project["id"]) == before


@pytest.mark.parametrize("kind", ["labels", "epics"])
def test_metadata_paging_and_cursor_scope(created_project, client_for, actors, foreign_scope, kind):
    leader = client_for(actors["leader"])
    route = f"/projects/{created_project['id']}/{kind}/"
    records = []
    for number in range(3):
        body = {"name": f"Item {number}"}
        if kind == "labels":
            body["color"] = "#123456"
        reply = leader.post(route, body, format="json")
        assert reply.status_code == 201, reply.content
        records.append(reply.json()["data"])
    before = effect_state(created_project["id"])
    first = leader.get(route, {"page_size": 1}).json()
    assert first["data"] == [records[-1]]
    assert first["meta"]["pagination"]["total_count"] == 3
    cursor = first["meta"]["pagination"]["next_cursor"]
    second = leader.get(route, {"page_size": 2, "cursor": cursor}).json()
    assert second["data"] == list(reversed(records[:-1]))
    assert second["meta"]["pagination"]["has_next"] is False
    for target, client in [
        (route, client_for(actors["teacher"])),
        (f"/projects/{foreign_scope[0]['id']}/{kind}/", leader),
        (route.replace("/" + kind + "/", "/epics/" if kind == "labels" else "/labels/"), leader),
    ]:
        response = client.get(target, {"cursor": cursor})
        assert response.status_code == 400, response.content
    assert effect_state(created_project["id"]) == before


@pytest.mark.parametrize("kind", ["labels", "epics"])
@pytest.mark.parametrize("actor", ["teacher", "outsider"])
def test_metadata_mutations_require_current_member(
    created_project, client_for, actors, kind, actor
):
    leader = client_for(actors["leader"])
    route = f"/projects/{created_project['id']}/{kind}/"
    body = {"name": "Original", **({"color": "#123456"} if kind == "labels" else {})}
    created = leader.post(route, body, format="json")
    assert created.status_code == 201, created.content
    row_id = created.json()["data"]["id"]
    before = effect_state(created_project["id"])
    client = client_for(actors[actor])
    for response in [
        client.post(route, {**body, "name": "Denied"}, format="json"),
        client.patch(route + row_id + "/", {"name": "Denied"}, format="json"),
        client.delete(route + row_id + "/"),
    ]:
        assert response.status_code == (403 if actor == "teacher" else 404), response.content
    model = Label if kind == "labels" else Epic
    row = model.objects.get(pk=row_id)
    assert row.name == "Original" and row.deleted_at is None
    assert effect_state(created_project["id"]) == before


@pytest.mark.parametrize("kind", ["labels", "epics"])
def test_metadata_unique_conflict_rolls_back_changes_and_audit(
    created_project, actors, client_for, kind
):
    leader = client_for(actors["leader"])
    route = f"/projects/{created_project['id']}/{kind}/"
    body = {"name": "Original", **({"color": "#123456"} if kind == "labels" else {})}
    original = leader.post(route, body, format="json").json()["data"]
    assert leader.post(route, {**body, "name": "Taken"}, format="json").status_code == 201
    before = effect_state(created_project["id"])
    model = Label if kind == "labels" else Epic
    persisted = model.objects.filter(pk=original["id"]).values().get()
    collision = leader.patch(
        route + original["id"] + "/",
        {"description": "Must roll back", "name": "Taken"},
        format="json",
    )
    assert collision.status_code == 409, collision.content
    assert collision.json()["error"]["code"] == (
        "LABEL_NAME_EXISTS" if kind == "labels" else "EPIC_NAME_EXISTS"
    )
    assert model.objects.filter(pk=original["id"]).values().get() == persisted
    assert effect_state(created_project["id"]) == before
    assert original in leader.get(route).json()["data"]


@pytest.mark.parametrize("resource", ["labels", "epics", "comments", "attachments"])
@pytest.mark.parametrize("scope_loss", ["wrong-teacher-class", "inactive-member"])
def test_project_read_routes_recheck_scope(
    created_project, client_for, actors, classroom, resource, scope_loss
):
    project_id = created_project["id"]
    if scope_loss == "wrong-teacher-class":
        classroom.teachers[actors["teacher"]] = ["other-group"]
        client = client_for(actors["teacher"])
    else:
        Project.objects.get(pk=project_id).members.filter(user_id=actors["member"]).update(
            status="REMOVED", left_at=timezone.now()
        )
        client = client_for(actors["member"])
    before = effect_state(project_id)
    response = client.get(f"/projects/{project_id}/{resource}/")
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert effect_state(project_id) == before


@pytest.mark.parametrize(
    "operation",
    ["label-update", "comment-create", "comment-update", "attachment-confirm", "attachment-delete"],
)
@pytest.mark.django_db(transaction=True)
def test_project_write_outbox_failure_rolls_back_subject_audit_and_receipt(
    project_upload, reject_outbox_event, client_for, actors, operation
):
    uploader, file_route, attachment = project_upload
    project_id = str(attachment.project_id)
    comments = "/comments/"
    content = {
        "project_id": project_id,
        "content_html": "Original",
        "mentioned_user_ids": [str(actors["member"])],
    }
    if operation == "label-update":
        labels = f"/projects/{project_id}/labels/"
        row = uploader.post(labels, {"name": "Original", "color": "#123456"}, format="json").json()[
            "data"
        ]
        route, method, payload = (
            labels + row["id"] + "/",
            "patch",
            {"name": "Changed", "color": "#abcdef"},
        )
        event_type = "label.updated"
    elif operation == "comment-create":
        route, method, payload, event_type = comments, "post", content, "comment.created"
    elif operation == "comment-update":
        row = uploader.post(comments, content, format="json").json()["data"]
        route, method = f"/comments/{row['id']}/", "patch"
        payload = {"content_html": "Changed", "mentioned_user_ids": [str(actors["leader"])]}
        event_type = "comment.updated"
    else:
        route, method = file_route, "post"
        payload, event_type = {"attachment_id": str(attachment.pk)}, "attachment.confirmed"
        if operation == "attachment-delete":
            assert (
                uploader.post(
                    route, payload, format="json", HTTP_IDEMPOTENCY_KEY="setup"
                ).status_code
                == 200
            )
            route, method, payload, event_type = (
                file_route + str(attachment.pk) + "/",
                "delete",
                {},
                "attachment.deleted",
            )
    before = effect_state(project_id)
    subject_state = {
        model: list(model.objects.order_by("pk").values())
        for model in [Label, Comment, CommentMention, Attachment]
    }
    with reject_outbox_event(event_type):
        response = getattr(uploader, method)(
            route, payload, format="json", HTTP_IDEMPOTENCY_KEY="failure"
        )
    assert response.status_code == 500, response.content
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert effect_state(project_id) == before
    assert all(
        list(model.objects.order_by("pk").values()) == rows for model, rows in subject_state.items()
    )
    assert not IdempotencyRecord.objects.filter(idempotency_key="failure").exists()


def test_project_teacher_feedback_is_readable_without_mutating_task(task_api, client_for, actors):
    _, _, create = task_api
    task = create()
    task_before = Task.objects.filter(pk=task["id"]).values().get()
    teacher = client_for(actors["teacher"])
    created = teacher.post(
        "/comments/",
        {
            "project_id": task["project_id"],
            "content_html": "<script>x</script><p>Hướng dẫn</p>",
            "mentioned_user_ids": [str(actors["member"])],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    data = created.json()["data"]
    comment = Comment.objects.get(pk=data["id"])
    assert comment.task_id is None and str(comment.project_id) == task["project_id"]
    assert comment.is_teacher_feedback and data["is_teacher_feedback"]
    assert data["content_html"] == "<p>Hướng dẫn</p>" and data["content_stripped"] == "Hướng dẫn"
    assert comment.mentions.get().user_id == actors["member"]
    assert client_for(actors["member"]).get(f"/projects/{task['project_id']}/comments/").json()[
        "data"
    ] == [data]
    assert teacher.get(f"/tasks/{task['id']}/comments/").json()["data"] == []
    feedback = OutboxEvent.objects.get(event_type="teacher.feedback.added")
    assert_event_contract(feedback)
    assert_event_contract(OutboxEvent.objects.get(event_type="comment.mentions.added"))
    assert feedback.data["data"]["id"] == data["id"]
    assert feedback.data["data"]["task_id"] is None
    assert feedback.data["data"]["scope_source_version"] == 1
    assert set(feedback.data["data"]["recipient_ids"]) == {
        str(actors["leader"]),
        str(actors["member"]),
    }
    assert Activity.objects.get(comment=comment, verb="created").actor_user_id == actors["teacher"]
    assert Task.objects.filter(pk=task["id"]).values().get() == task_before


@pytest.mark.parametrize("invalid", ["no-subject", "both-subjects", "spoof-feedback"])
def test_comment_subject_and_actor_fields_validation_has_no_effect(
    task_api, actors, client_for, invalid
):
    _, _, create = task_api
    task = create()
    body = {"content_html": "Rejected", "project_id": task["project_id"]}
    if invalid == "no-subject":
        body.pop("project_id")
    elif invalid == "both-subjects":
        body["task_id"] = task["id"]
    else:
        body["is_teacher_feedback"] = True
    before = effect_state(task["project_id"])
    response = client_for(actors["member"]).post("/comments/", body, format="json")
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not Comment.objects.exists() and not CommentMention.objects.exists()
    assert effect_state(task["project_id"]) == before


def test_removed_project_uploader_cannot_replay_receipt_or_download(project_upload):
    uploader, route, row = project_upload
    body = {"attachment_id": str(row.pk)}
    confirmed = uploader.post(
        route, body, format="json", HTTP_IDEMPOTENCY_KEY="receipt-before-removal"
    )
    assert confirmed.status_code == 200, confirmed.content
    Project.objects.get(pk=row.project_id).members.filter(user_id=row.uploaded_by_user_id).update(
        status="REMOVED", left_at=timezone.now()
    )
    before = effect_state(row.project_id)
    replay = uploader.post(
        route, body, format="json", HTTP_IDEMPOTENCY_KEY="receipt-before-removal"
    )
    assert replay.status_code == 404, replay.content
    assert uploader.get(route + str(row.pk) + "/download/").status_code == 404
    assert uploader.delete(route + str(row.pk) + "/").status_code == 404
    row.refresh_from_db()
    assert row.status == "CONFIRMED" and row.deleted_at is None
    assert effect_state(row.project_id) == before


def test_project_file_list_pages_only_current_confirmed_subjects(
    project_upload, task_api, client_for, actors, foreign_scope
):
    uploader, route, first = project_upload
    leader, _, create = task_api
    task = create()
    other_project, _ = foreign_scope

    def upload(client, destination, name):
        presigned = client.post(
            destination + "presigned-url/",
            {"file_name": name, "file_size": 1, "content_type": "text/plain"},
            format="json",
        )
        assert presigned.status_code == 200, presigned.content
        attachment_id = presigned.json()["data"]["attachment_id"]
        reply = client.post(
            destination,
            {"attachment_id": attachment_id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="confirm-" + name,
        )
        assert reply.status_code == 200, reply.content
        return reply.json()["data"]

    first_response = uploader.post(
        route, {"attachment_id": str(first.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="first"
    )
    assert first_response.status_code == 200, first_response.content
    second = upload(uploader, route, "second.txt")
    task_file = upload(uploader, f"/tasks/{task['id']}/attachments/", "task.txt")
    foreign_file = upload(leader, f"/projects/{other_project['id']}/attachments/", "foreign.txt")
    pending = uploader.post(
        route + "presigned-url/",
        {"file_name": "pending.txt", "file_size": 1, "content_type": "text/plain"},
        format="json",
    ).json()["data"]["attachment_id"]
    before = effect_state(first.project_id)
    page = uploader.get(route, {"page_size": 1}).json()
    assert page["data"] == [second] and page["meta"]["pagination"]["total_count"] == 2
    tail = uploader.get(route, {"cursor": page["meta"]["pagination"]["next_cursor"]}).json()
    assert tail["data"] == [first_response.json()["data"]]
    assert not tail["meta"]["pagination"]["has_next"]
    assert not {task_file["id"], foreign_file["id"], pending} & {
        item["id"] for item in page["data"] + tail["data"]
    }
    assert effect_state(first.project_id) == before
    assert uploader.delete(route + str(first.pk) + "/").status_code == 200
    listed = client_for(actors["teacher"]).get(route).json()
    assert listed["data"] == [second] and listed["meta"]["pagination"]["total_count"] == 1


def test_active_member_cannot_create_epic_or_edit_another_lead_epic(
    created_project, actors, client_for
):
    leader, member = client_for(actors["leader"]), client_for(actors["member"])
    route = f"/projects/{created_project['id']}/epics/"
    created = leader.post(
        route, {"name": "Leader epic", "lead_user_id": str(actors["leader"])}, format="json"
    )
    assert created.status_code == 201, created.content
    epic_id = created.json()["data"]["id"]
    before = effect_state(created_project["id"])
    for response in [
        member.post(route, {"name": "Denied"}, format="json"),
        member.patch(route + epic_id + "/", {"name": "Denied"}, format="json"),
        member.delete(route + epic_id + "/"),
    ]:
        assert response.status_code == 403, response.content
    assert Epic.objects.get(pk=epic_id).name == "Leader epic"
    assert member.get(route).json()["data"] == [created.json()["data"]]
    assert effect_state(created_project["id"]) == before


@pytest.mark.parametrize(
    ("kind", "invalid", "status", "code"),
    [
        ("labels", "color", 400, "VALIDATION_ERROR"),
        ("labels", "name-length", 400, "VALIDATION_ERROR"),
        ("labels", "client-project", 400, "VALIDATION_ERROR"),
        ("epics", "date-order", 400, "VALIDATION_ERROR"),
        ("epics", "status", 400, "VALIDATION_ERROR"),
        ("epics", "foreign-lead", 422, "MEMBER_NOT_ACTIVE"),
    ],
)
def test_metadata_input_validation_never_writes_subject_or_side_effect(
    created_project, foreign_scope, actors, client_for, kind, invalid, status, code
):
    leader = client_for(actors["leader"])
    body = {"name": "Rejected", **({"color": "#123456"} if kind == "labels" else {})}
    body.update(
        {
            "color": {"color": "#12345G"},
            "name-length": {"name": "x" * 51},
            "client-project": {"project_id": foreign_scope[0]["id"]},
            "date-order": {"start_date": "2027-02-01", "target_date": "2027-01-01"},
            "status": {"status": "DONE"},
            "foreign-lead": {"lead_user_id": str(actors["outsider"])},
        }[invalid]
    )
    before = effect_state(created_project["id"])
    response = leader.post(f"/projects/{created_project['id']}/{kind}/", body, format="json")
    assert response.status_code == status, response.content
    assert response.json()["error"]["code"] == code
    assert not Label.objects.exists() and not Epic.objects.exists()
    assert effect_state(created_project["id"]) == before
