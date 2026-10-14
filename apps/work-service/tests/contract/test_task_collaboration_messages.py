from uuid import uuid4

import pytest

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
    reply = client.post("/api/v1/comments/", body, format="json")
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert reply.json()["message"] == message and reply.json()["error"]["details"] == []
    assert effect_state(task["project_id"]) == before
