from uuid import uuid4

import pytest
from rest_framework.test import APIClient

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def test_success_business_and_framework_messages_are_vietnamese(
    section, actors, client_for, post_command
):
    teacher = client_for(actors["teacher"])
    success = post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1})
    assert (
        success.status_code == 200
        and success.json()["message"] == "Đã chốt giai đoạn lập nhóm của lớp học."
    )
    business = post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1})
    assert business.status_code == 409 and business.json()["error"]["code"] == "VERSION_CONFLICT"
    assert "tải lại" in business.json()["message"]
    framework = post_command(teacher, "/classes/", {})
    assert framework.status_code == 400
    assert all(
        row["issue"] == "Trường này là bắt buộc." for row in framework.json()["error"]["details"]
    )
    malformed = teacher.post("/classes/", '{"broken":', content_type="application/json")
    assert malformed.status_code == 400 and "không đúng định dạng" in malformed.json()["message"]
    for reply in (success, business, framework, malformed):
        assert set(reply.json()) == {"success", "message", "data", "meta", "error"}
        assert not any(
            term in reply.json()["message"]
            for term in ["Traceback", "SQL", "Classroom", "mock", "uploader"]
        )


@pytest.mark.parametrize("status", [404, 405, 415])
def test_routing_and_media_errors_keep_vietnamese_envelope(identity, client_for, actors, status):
    client = client_for(actors["teacher"])
    if status == 404:
        response = APIClient().get("/missing-classroom-resource/")
    elif status == 405:
        response = client.delete("/classes/")
    else:
        response = client.post("/classes/", "not-json", content_type="text/plain")
    assert response.status_code == status
    assert response.json()["success"] is False
    assert response.json()["data"] is None
    assert set(response.json()) == {"success", "message", "data", "meta", "error"}
    assert all(
        word not in response.json()["message"]
        for word in ("Method", "Unsupported", "Not found", "Classroom", "Traceback")
    )


def test_missing_class_returns_resource_not_found_message(client_for, actors):
    response = client_for(actors["teacher"]).get(f"/classes/{uuid4()}/")

    assert response.status_code == 404
    assert response.json()["message"] == "Không tìm thấy tài nguyên yêu cầu."
    assert response.json()["error"] == {"code": "RESOURCE_NOT_FOUND", "details": []}
