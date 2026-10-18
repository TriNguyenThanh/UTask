import pytest
from django.db import DatabaseError
from django.http import Http404
from psycopg import errors
from rest_framework.exceptions import NotFound, PermissionDenied

from common.errors import ClassroomError, database_error
from common.exception_handler import exception_handler
from common.serializers import StrictInputSerializer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "driver_error", [errors.LockNotAvailable, errors.DeadlockDetected, errors.SerializationFailure]
)
def test_database_concurrency_error_maps_to_retryable_conflict(driver_error):
    wrapped = DatabaseError("database boundary")
    wrapped.__cause__ = driver_error("details not exposed")
    error = database_error(wrapped)
    assert error.code == "CONCURRENT_MUTATION_IN_PROGRESS" and error.status_code == 409
    assert "details not exposed" not in str(error)


def test_framework_permission_denial_keeps_error_envelope_and_status():
    response = exception_handler(PermissionDenied("Denied"), {})
    assert response.status_code == 403 and response.data["error"]["code"] == "PERMISSION_DENIED"
    assert response.data["data"] is None and response.data["success"] is False


@pytest.mark.parametrize("value", [[], ["wrong-object"], 42, "text"])
def test_strict_input_serializer_rejects_non_object_bodies(value):
    serializer = StrictInputSerializer(data=value)
    assert not serializer.is_valid()
    assert serializer.errors["non_field_errors"]


@pytest.mark.parametrize(
    "error, expected_message",
    [
        (Http404("No ClassSection matches the given query."), "Không tìm thấy tài nguyên yêu cầu."),
        (NotFound("Not found."), "Không tìm thấy tài nguyên yêu cầu."),
        (NotFound(), "Không tìm thấy."),
        (NotFound("Không tìm thấy lớp học."), "Không tìm thấy lớp học."),
        (
            ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy nhóm học tập.", 404),
            "Không tìm thấy nhóm học tập.",
        ),
    ],
)
def test_not_found_errors_describe_missing_resource_without_exposing_diagnostics(
    error, expected_message
):
    response = exception_handler(error, {})

    assert response.status_code == 404
    assert response.data["message"] == expected_message
    assert response.data["error"] == {"code": "RESOURCE_NOT_FOUND", "details": []}
    assert response.data["data"] is None
    assert response.data["success"] is False
