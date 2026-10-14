from uuid import uuid4

import pytest
from django.db import transaction
from rest_framework.exceptions import Throttled, ValidationError

from apps.messaging.services import emit_event
from apps.projects.models import Project
from common.exception_handler import exception_handler
from common.responses import build_envelope

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def test_serializer_uuid_payload_persists_same_json_as_runtime(created_project):
    raw_uuid = uuid4()
    envelope = build_envelope({"id": raw_uuid, "nested": {"project_id": raw_uuid}})
    assert envelope["data"] == {"id": str(raw_uuid), "nested": {"project_id": str(raw_uuid)}}
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=created_project["id"])
        event = emit_event(
            project, "task.created", {"id": raw_uuid}, aggregate_type="task", aggregate_id=raw_uuid
        )
    event.refresh_from_db()
    assert event.data["data"]["id"] == str(raw_uuid)


def test_exception_details_are_plain_messages_and_retry_after_survives():
    response = exception_handler(ValidationError({"name": ["Thiếu tên."]}), {})
    assert response.status_code == 400
    assert response.data["error"]["details"] == [{"field": "name", "issue": "Thiếu tên."}]
    assert (
        response.data["message"] == "Dữ liệu yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin."
    )
    drf_req = exception_handler(ValidationError({"title": ["This field is required."]}), {})
    assert drf_req.data["error"]["details"] == [
        {"field": "title", "issue": "Trường này là bắt buộc."}
    ]
    assert (
        drf_req.data["message"] == "Dữ liệu yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin."
    )
    throttled = exception_handler(Throttled(wait=7), {})
    assert throttled.status_code == 429 and throttled["Retry-After"] == "7"
