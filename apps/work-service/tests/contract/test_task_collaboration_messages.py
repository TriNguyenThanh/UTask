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
