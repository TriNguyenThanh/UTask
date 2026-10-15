from uuid import uuid4

import pytest

from apps.messaging.models import IdempotencyRecord
from apps.projects.models import Project
from apps.tasks.models import Task
from tests.fixtures.ai_proposals import action_payload, backlog_payload
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize(
    "field,value,issue",
    [
        ("state_id", "bad", "Mã trạng thái phải là UUID hợp lệ."),
        ("epic_id", "bad", "Mã mục tiêu lớn phải là UUID hợp lệ."),
        ("parent_id", "bad", "Mã công việc cha phải là UUID hợp lệ."),
        ("assignee_id", "bad", "Mã người phụ trách phải là UUID hợp lệ."),
        ("label_id", "bad", "Mã nhãn phải là UUID hợp lệ."),
        ("type", "bad", "Loại công việc không hợp lệ."),
        ("priority", "bad", "Mức ưu tiên không hợp lệ."),
        ("is_blocked", "bad", "Trạng thái chặn phải là true hoặc false."),
        ("due_date_from", "bad", "Ngày bắt đầu lọc phải là ngày hợp lệ."),
        ("due_date_to", "bad", "Ngày kết thúc lọc phải là ngày hợp lệ."),
    ],
)
def test_filter_validation_is_vietnamese_without_html_and_has_no_effect(
    task_api, field, value, issue
):
    leader, route, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.get(route, {field: value})
    assert reply.status_code == 400
    assert reply.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": field, "issue": issue}],
    }
    assert "<" not in reply.json()["message"] and "<" not in issue
    assert effect_state(task["project_id"]) == before


def test_label_pattern_validation_is_vietnamese_and_has_no_effect(task_api):
    leader, route, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.post(
        route.rsplit("tasks/", 1)[0] + "labels/", {"name": "Bad", "color": "red"}, format="json"
    )
    assert reply.status_code == 400
    assert reply.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [
            {
                "field": "color",
                "issue": "Màu nhãn phải gồm dấu # và 6 ký tự thập lục phân (0–9, A–F).",
            }
        ],
    }
    assert effect_state(task["project_id"]) == before


@pytest.mark.parametrize(
    "kind", ["task", "subtask", "backlog", "ai-subtask", "action", "attachment"]
)
def test_receipted_success_message_is_persisted_and_replayed_without_mutation(
    task_api, actors, client_for, pending_file, ai, kind
):
    leader, route, create = task_api
    task = create()
    project = Project.objects.get(pk=task["project_id"])
    if kind == "task":
        body, message, status = {"title": "Created"}, "Đã tạo công việc.", 201
    elif kind == "subtask":
        route = f"/tasks/{task['id']}/subtasks/"
        body, message, status = {"title": "Child"}, "Đã tạo công việc con.", 201
    elif kind in {"backlog", "ai-subtask"}:
        body = backlog_payload(project)
        if kind == "ai-subtask":
            ai(project.pk, kind="SUBTASK", parent_id=task["id"])
            route = f"/tasks/{task['id']}/subtasks/bulk-apply-ai/"
            body["subtasks"] = body.pop("tasks")
            body["expected_parent_version"] = 1
            body.pop("expected_project_version")
        else:
            ai(project.pk)
            route += "bulk-apply-ai/"
        message, status = "Đã tạo các công việc từ đề xuất đã duyệt.", 201
    elif kind == "action":
        ai(project.pk, kind="ACTION", targets=[task["id"]])
        route = f"/projects/{project.pk}/ai-actions/apply/"
        body = action_payload(
            {
                "kind": "SET_PRIORITY",
                "task_id": task["id"],
                "expected_version": 1,
                "priority": "HIGH",
            }
        )
        message, status = "Đã áp dụng các thay đổi trong đề xuất đã duyệt.", 200
    else:
        leader, task, route, row = pending_file
        body = {"attachment_id": str(row.pk)}
        message, status = "Tệp đính kèm đã được tải lên và xác nhận hoàn tất.", 200
    first = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="message-replay")
    assert first.status_code == status, first.content
    assert first.json()["message"] == message
    receipt = IdempotencyRecord.objects.get(endpoint_path=route, idempotency_key="message-replay")
    assert receipt.response_body == first.json()
    before = effect_state(task["project_id"])
    tasks = list(Task.objects.order_by("id").values())
    replay = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="message-replay")
    assert replay.status_code == status and replay.json() == first.json()
    assert effect_state(task["project_id"]) == before
    assert list(Task.objects.order_by("id").values()) == tasks


@pytest.mark.parametrize("kind", ["task", "comment", "ai"])
def test_list_length_validation_is_vietnamese_without_writes(task_api, kind):
    leader, route, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    if kind == "task":
        body = {"title": "Bad", "assignee_ids": [str(uuid4())] * 101}
        expected_field, issue = (
            "assignee_ids",
            "Danh sách người phụ trách không được vượt quá 100 mục.",
        )
    elif kind == "comment":
        route = "/comments/"
        body = {
            "task_id": task["id"],
            "content_html": "Hi",
            "mentioned_user_ids": [str(uuid4())] * 101,
        }
        expected_field, issue = (
            "mentioned_user_ids",
            "Danh sách người được nhắc tên không được vượt quá 100 mục.",
        )
    else:
        route += "bulk-apply-ai/"
        body = {
            "proposal_id": "p",
            "context_version": 0,
            "expected_project_version": 1,
            "tasks": [],
        }
        expected_field, issue = (
            "tasks.non_field_errors",
            "Vui lòng chọn ít nhất một công việc trong đề xuất.",
        )
    reply = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY="bad-message")
    assert reply.status_code == 400, reply.content
    assert reply.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": expected_field, "issue": issue}],
    }
    assert effect_state(task["project_id"]) == before


def test_task_comment_and_file_messages_describe_saved_outcome_and_business_errors(
    task_api, storage
):
    leader, route, create = task_api
    task = create()
    detail = f"/tasks/{task['id']}/"
    changed = leader.patch(detail, {"expected_version": 1, "title": "Updated"}, format="json")
    assert changed.status_code == 200 and changed.json()["message"] == "Đã cập nhật công việc."
    assert Task.objects.get(pk=task["id"]).title == "Updated"
    no_change = leader.patch(detail, {"expected_version": 2, "title": "Updated"}, format="json")
    assert (
        no_change.status_code == 200
        and no_change.json()["message"] == "Công việc không có thay đổi."
    )
    before = effect_state(task["project_id"])
    conflict = leader.patch(detail, {"expected_version": 1, "title": "Stale"}, format="json")
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "VERSION_CONFLICT"
    assert (
        conflict.json()["message"]
        == "Công việc đã có thay đổi bởi thao tác khác, vui lòng tải lại dữ liệu."
    )
    assert effect_state(task["project_id"]) == before
    for url, message in [
        (route, "Đã tải danh sách công việc."),
        (detail, "Đã tải chi tiết công việc."),
        (detail + "activities/", "Đã tải lịch sử công việc."),
        (detail + "comments/", "Đã tải danh sách bình luận."),
        (detail + "attachments/", "Đã tải danh sách tệp đính kèm."),
    ]:
        reply = leader.get(url)
        assert reply.status_code == 200 and reply.json()["message"] == message
    comment = leader.post(
        "/comments/", {"task_id": task["id"], "content_html": "Comment"}, format="json"
    )
    assert comment.status_code == 201 and comment.json()["message"] == "Đã gửi bình luận."
    comment_route = f"/comments/{comment.json()['data']['id']}/"
    edited = leader.patch(comment_route, {"content_html": "Edited"}, format="json")
    assert edited.status_code == 200 and edited.json()["message"] == "Đã cập nhật bình luận."
    removed = leader.delete(comment_route)
    assert removed.status_code == 200 and removed.json()["message"] == "Đã xóa bình luận."


@pytest.mark.parametrize("operation", ["feedback", "mention"])
def test_collaboration_verification_error_explains_outcome_without_dependency_diagnostics(
    task_api, actors, client_for, classroom, monkeypatch, operation
):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    if operation == "feedback":
        monkeypatch.delattr(classroom, "teacher_feedback_scope")
        client = client_for(actors["teacher"])
        body = {"task_id": task["id"], "content_html": "Feedback"}
        message = "Chưa thể xác minh quyền gửi nhận xét của bạn."
    else:
        client = leader
        body = {
            "task_id": task["id"],
            "content_html": "Mention",
            "mentioned_user_ids": [str(uuid4())],
        }
        message = "Chưa thể xác minh người được nhắc tên có quyền xem nội dung này."
    reply = client.post("/comments/", body, format="json")
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert reply.json()["message"] == message and reply.json()["error"]["details"] == []
    assert effect_state(task["project_id"]) == before
