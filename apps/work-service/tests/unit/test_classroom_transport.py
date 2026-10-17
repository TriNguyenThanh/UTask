from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests
from django.utils import timezone

from apps.projects.serializers.projects import CreateProjectSerializer
from common.authentication import Actor
from common.errors import WorkError
from infrastructure.classroom import RemoteClassroom

pytestmark = pytest.mark.unit


def snapshot_data(actor):
    return {
        "group_id": str(uuid4()),
        "class_id": str(uuid4()),
        "source_version": 2,
        "members": [{"user_id": str(actor.id), "role": "LEADER", "status": "ACTIVE"}],
    }


def test_authenticated_snapshot_and_service_recovery_never_reuse_bearer(classroom_http):
    actor = Actor(uuid4(), access_token="request-only-token")
    data = classroom_http["data"] = snapshot_data(actor)
    client = RemoteClassroom()
    assert client.group_snapshot(data["group_id"], actor).source_version == 2
    assert client.recovery_snapshot(data["group_id"]).class_id == data["class_id"]
    first, recovery = classroom_http["calls"]
    assert first[2]["headers"]["Authorization"] == "Bearer request-only-token"
    assert recovery[2]["headers"] == {"X-Service-Key": "test-classroom-key"}
    assert first[2]["timeout"] == (2, 5) and first[2]["allow_redirects"] is False
    assert "request-only-token" not in repr(actor)


@pytest.mark.parametrize(
    "case", ["redirect", "timeout", "wrong-group", "bad-members", "bool-version"]
)
def test_snapshot_transport_and_binding_fail_closed(classroom_http, case):
    actor = Actor(uuid4(), access_token="request-only-token")
    data = classroom_http["data"] = snapshot_data(actor)
    group_id = data["group_id"]
    if case == "redirect":
        classroom_http["status"] = 302
    elif case == "timeout":
        classroom_http["error"] = requests.Timeout()
    elif case == "wrong-group":
        data["group_id"] = str(uuid4())
    elif case == "bad-members":
        data["members"].append(data["members"][0])
    else:
        data["source_version"] = True
    with pytest.raises(WorkError) as error:
        RemoteClassroom().group_snapshot(group_id, actor)
    assert error.value.code == "CLASSROOM_UNAVAILABLE"


@pytest.mark.parametrize("status", [401, 403, 404, 409, 422])
def test_authority_errors_preserve_http_status(classroom_http, status):
    classroom_http["status"] = status
    with pytest.raises(WorkError) as error:
        RemoteClassroom().teacher_group_ids(Actor(uuid4(), access_token="token"))
    assert error.value.status_code == status


def test_teacher_groups_are_authority_facts_with_uuid_ids(classroom_http):
    actor = Actor(uuid4(), access_token="token")
    classroom_http["data"] = {"group_ids": []}
    assert RemoteClassroom().teacher_group_ids(actor) == []
    group_id = str(uuid4())
    classroom_http["data"] = {"group_ids": [group_id, group_id]}
    with pytest.raises(WorkError):
        RemoteClassroom().teacher_group_ids(actor)


@pytest.mark.parametrize("invalid", [None, "expired", "actor", "project", "group"])
def test_feedback_scope_accepts_current_binding_and_rejects_invalid_facts(classroom_http, invalid):
    actor = Actor(uuid4(), access_token="token")
    project = SimpleNamespace(pk=uuid4(), classroom_group_id=str(uuid4()))
    data = classroom_http["data"] = {
        "actor_id": str(actor.id),
        "project_id": str(project.pk),
        "group_id": project.classroom_group_id,
        "source_version": 3,
        "expires_at": (timezone.now() + timedelta(seconds=60)).isoformat(),
    }
    if invalid == "expired":
        data["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    elif invalid is not None:
        data[invalid + "_id"] = str(uuid4())
    if invalid:
        with pytest.raises(WorkError):
            RemoteClassroom().teacher_feedback_scope(project, actor)
    else:
        assert RemoteClassroom().teacher_feedback_scope(project, actor).source_version == 3


@pytest.mark.parametrize(
    "invalid", [None, "expired", "actor", "group", "version", "users", "expiry"]
)
def test_mention_scope_returns_allowed_users_and_rejects_invalid_facts(classroom_http, invalid):
    actor = Actor(uuid4(), access_token="token")
    group_id = str(uuid4())
    allowed = uuid4()
    data = classroom_http["data"] = {
        "actor_id": str(actor.id),
        "group_id": group_id,
        "source_version": 3,
        "expires_at": (timezone.now() + timedelta(seconds=60)).isoformat(),
        "mentionable_user_ids": [str(allowed)],
    }
    if invalid == "expired":
        data["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    elif invalid in {"actor", "group"}:
        data[invalid + "_id"] = str(uuid4())
    elif invalid == "version":
        data["source_version"] = True
    elif invalid == "users":
        data["mentionable_user_ids"] = ["invalid-user-id"]
    elif invalid == "expiry":
        data["expires_at"] = "not-a-date"
    if invalid:
        with pytest.raises(WorkError) as error:
            RemoteClassroom().teacher_mention_ids(group_id, {allowed}, actor)
        assert error.value.code == "CLASSROOM_UNAVAILABLE"
    else:
        assert RemoteClassroom().teacher_mention_ids(group_id, {allowed, uuid4()}, actor) == {
            allowed
        }


def test_missing_actor_or_service_credential_fails_closed(classroom_http, settings):
    with pytest.raises(WorkError):
        RemoteClassroom().teacher_group_ids(Actor(uuid4()))
    settings.CLASSROOM_WORK_SERVICE_KEY = ""
    with pytest.raises(WorkError):
        RemoteClassroom().recovery_snapshot(uuid4())
    assert classroom_http["calls"] == []


def test_invalid_requested_group_is_validation_error_without_http_call(classroom_http):
    with pytest.raises(WorkError) as error:
        RemoteClassroom().group_snapshot("not-a-uuid", Actor(uuid4(), access_token="token"))
    assert error.value.code == "VALIDATION_ERROR" and error.value.status_code == 400
    assert classroom_http["calls"] == []


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("ABCDEFAB-1234-1234-1234-123456789ABC", "abcdefab-1234-1234-1234-123456789abc"),
        ("group-1", "group-1"),
        ("not-a-uuid", "not-a-uuid"),
    ],
)
def test_project_group_id_normalization_preserves_adapter_logical_ids(given, expected):
    serializer = CreateProjectSerializer(
        data={"identifier": "UUID", "name": "Dự án", "classroom_group_id": given}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["classroom_group_id"] == expected


def test_snapshot_requested_uuid_case_is_normalized(classroom_http):
    actor = Actor(uuid4(), access_token="request-only-token")
    data = classroom_http["data"] = snapshot_data(actor)
    assert (
        RemoteClassroom().group_snapshot(data["group_id"].upper(), actor).group_id
        == data["group_id"]
    )
