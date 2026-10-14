from uuid import uuid4

import pytest
from django.db import transaction
from rest_framework.exceptions import (
    ErrorDetail,
    NotAuthenticated,
    ParseError,
    Throttled,
    ValidationError,
)
from rest_framework.test import APIClient

from apps.messaging.models import IdempotencyRecord
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from common.errors import WorkError
from common.exception_handler import exception_handler
from common.responses import build_envelope
from tests.fixtures.transactions import effect_state

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "issue",
    [
        "This value does not match the required pattern.",
        '<ul class="errorlist"><li>Enter a valid UUID.</li></ul>',
        "database driver diagnostic: hidden",
    ],
)
def test_framework_and_business_validation_issues_are_plain_vietnamese(issue):
    for exception in [
        ValidationError({"color": [ErrorDetail(issue, code="invalid")]}),
        WorkError(
            "VALIDATION_ERROR",
            "Thông tin không hợp lệ.",
            details=[{"field": "color", "issue": issue}],
        ),
    ]:
        reply = exception_handler(exception, {})
        detail = reply.data["error"]["details"][0]
        assert reply.status_code == 400 and detail["field"] == "color"
        assert detail["issue"] == (
            "Giá trị không đúng định dạng yêu cầu."
            if issue.startswith("This value")
            else "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."
        )
        assert "<" not in detail["issue"] and "hidden" not in str(reply.data)


def test_framework_headers_and_json_parser_diagnostics_are_preserved_or_hidden():
    unauthenticated = NotAuthenticated()
    unauthenticated.auth_header = "Bearer"
    denied = exception_handler(unauthenticated, {})
    assert denied.status_code == 401 and denied["WWW-Authenticate"] == "Bearer"
    throttled = exception_handler(Throttled(wait=7), {})
    assert throttled.status_code == 429 and throttled["Retry-After"] == "7"
    assert throttled.data["message"] == "Bạn đã gửi quá nhiều yêu cầu. Vui lòng chờ rồi thử lại."
    malformed = exception_handler(ParseError("JSON parse error - hidden-decoder-detail"), {})
    assert malformed.status_code == 400 and "hidden-decoder-detail" not in str(malformed.data)
    assert malformed.data["message"] == "Dữ liệu yêu cầu gửi lên không đúng định dạng."


@pytest.mark.django_db(transaction=True)
def test_receipt_message_commits_with_result_and_replay_keeps_original_envelope(actors):
    scope = {
        "user_id": actors["leader"],
        "http_method": "POST",
        "endpoint_path": "/api/v1/projects/",
        "idempotency_key": "outcome-message",
    }
    with transaction.atomic():
        claim_receipt(scope, {})
        first = save_receipt(scope, {}, {"id": str(uuid4())}, status=201, message="Đã tạo dự án.")
    saved = IdempotencyRecord.objects.get()
    assert saved.response_body == first.data and saved.response_body["message"] == "Đã tạo dự án."
    assert replay_response(saved).data == first.data
    with transaction.atomic():
        replay = save_receipt(scope, {}, {"unexpected": True}, message="Đã đổi thông tin.")
    assert replay.status_code == 201 and replay.data == first.data
    legacy_scope = scope | {"idempotency_key": "legacy-call"}
    with transaction.atomic():
        legacy = save_receipt(legacy_scope, {}, {"saved": True})
    assert legacy.data == build_envelope({"saved": True})


@pytest.mark.django_db
def test_owned_read_outcomes_and_actual_auth_error_envelope(github, actors, client_for):
    _, _, repository, task = github
    client = client_for(actors["member"])
    routes = {
        "/api/v1/projects/": "Đã lấy danh sách dự án.",
        f"/api/v1/projects/{task.project_id}/": "Đã lấy thông tin dự án.",
        f"/api/v1/projects/{task.project_id}/members/": "Đã lấy danh sách thành viên dự án.",
        f"/api/v1/projects/{task.project_id}/states/": "Đã lấy danh sách cột trạng thái.",
        f"/api/v1/projects/{task.project_id}/kanban/": "Đã lấy bảng công việc của dự án.",
        f"/api/v1/projects/{task.project_id}/dashboard/": "Đã lấy số liệu công việc của dự án.",
        f"/api/v1/projects/{task.project_id}/sprints/": "Đã lấy danh sách chu kỳ làm việc.",
        repository: "Đã lấy thông tin kết nối kho mã nguồn của dự án.",
        f"/api/v1/tasks/{task.pk}/github-links/": "Đã lấy danh sách liên kết GitHub của công việc.",
    }
    before = effect_state(task.project_id)
    for route, message in routes.items():
        reply = client.get(route)
        assert reply.status_code == 200 and reply.json()["message"] == message
        assert set(reply.json()) == {"success", "message", "data", "meta", "error"}
    assert effect_state(task.project_id) == before
    denied = APIClient().get(repository)
    assert denied.status_code == 401 and denied["WWW-Authenticate"] == "Bearer"
    assert denied.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
