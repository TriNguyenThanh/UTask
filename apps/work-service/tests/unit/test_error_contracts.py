from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core import signing
from django.db import DatabaseError
from psycopg import errors
from rest_framework.exceptions import PermissionDenied

from apps.projects.queries.board import cursor_scope, decode_cursor
from common.authentication import Actor
from common.errors import WorkError, database_error
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


def test_valid_signature_does_not_make_nonnumeric_board_rank_acceptable():
    project = SimpleNamespace(pk=uuid4(), board_revision=1)
    actor = Actor(uuid4())
    state_id = uuid4()
    scope = cursor_scope(project, actor, state_id, {})
    token = signing.dumps(
        {**scope, "rank": "not-a-number", "task_id": str(uuid4())},
        salt="work-board-v1",
        compress=True,
    )
    with pytest.raises(WorkError) as error:
        decode_cursor(token, scope)
    assert error.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", [[], ["wrong-object"], 42, "text"])
def test_strict_input_serializer_rejects_non_object_bodies(value):
    serializer = StrictInputSerializer(data=value)
    assert not serializer.is_valid()
    assert serializer.errors["non_field_errors"]
