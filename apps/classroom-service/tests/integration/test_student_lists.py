from uuid import uuid4

import pytest
from django.db import DatabaseError, connection
from django.utils import timezone

from apps.courses.models import ClassTeacher, Enrollment
from apps.courses.services.enrollments import add_students
from apps.messaging.models import Activity, IdempotencyRecord
from common.errors import ClassroomError
from tests.fixtures.identity import provision_result, student_rows

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_result", []),
        ("account_result", {}),
        ("reason", []),
        ("reason", {}),
        ("account_status", []),
    ],
)
def test_malformed_provisioning_keeps_prepared_receipt_and_retries_same_upstream_key(
    section, actors, command_request, monkeypatch, field, value
):
    user_id = uuid4()
    rows = student_rows()
    valid = {
        **rows[0],
        "user_id": str(user_id),
        "account_status": "ACTIVE",
        "account_result": "EXISTING",
        "reason": None,
    }
    results = [{**valid, field: value}]
    calls = []

    class IdentityReply:
        status_code = 200

        def json(self):
            return {"success": True, "data": {"results": results}}

    def request(*args, **kwargs):
        assert not connection.in_atomic_block
        calls.append(kwargs["headers"]["Idempotency-Key"])
        return IdentityReply()

    monkeypatch.setattr("infrastructure.identity.requests.request", request)
    command = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    payload = {"students": rows}
    with pytest.raises(ClassroomError) as error:
        add_students(command, section.pk, payload)
    assert error.value.code == "IDENTITY_UNAVAILABLE" and error.value.status_code == 503
    receipt = IdempotencyRecord.objects.get()
    assert receipt.status == "PREPARED" and receipt.response_body is None
    assert not Enrollment.objects.filter(user_id=user_id).exists()
    assert not Activity.objects.exists()
    results[0] = valid
    response = add_students(command, section.pk, payload)
    assert response.data["data"]["summary"]["enrolled"] == 1
    assert calls == [str(receipt.upstream_key), str(receipt.upstream_key)]
    assert add_students(command, section.pk, payload).data == response.data
    assert len(calls) == 2 and Enrollment.objects.filter(user_id=user_id).count() == 1


def test_partial_enrollment_pending_accounts_duplicates_and_replay(
    section, actors, identity, command_request
):
    ids = [uuid4(), uuid4(), None]
    rows = student_rows(3)

    def provision(rows, key):
        assert not connection.in_atomic_block
        prepared = IdempotencyRecord.objects.get(upstream_key=key)
        assert prepared.status == "PREPARED" and prepared.response_body is None
        return provision_result(rows, ids)

    identity["provision"] = provision
    request = command_request(
        actors["teacher"], f"/classes/{section.pk}/students/", roles=("TEACHER",)
    )
    payload = {"students": rows}
    response = add_students(request, section.pk, payload)
    assert response.data["data"]["summary"] == {
        "total_records": 3,
        "enrolled": 2,
        "already_enrolled": 0,
        "failed": 1,
        "created_accounts": 2,
        "existing_accounts": 0,
        "flagged": 0,
        "duplicates": 0,
    }
    assert Enrollment.objects.filter(class_section=section, user_id__in=ids[:2]).count() == 2
    assert add_students(request, section.pk, payload).data == response.data
    assert len([call for call in identity["calls"] if call[0] == "provision"]) == 1
    assert Activity.objects.filter(verb="enrollment.added").count() == 2
    assert "password" not in str(response.data) and "activation_url" not in str(response.data)


def test_upstream_failure_preserves_stable_prepared_key_and_payload(
    section, actors, identity, command_request
):
    rows = student_rows()
    calls = []

    def provision(rows, key):
        calls.append((rows, key))
        assert not connection.in_atomic_block
        if len(calls) == 1:
            raise ClassroomError("IDENTITY_UNAVAILABLE", "Chưa thể xác minh tài khoản.", 503)
        return provision_result(rows, [uuid4()])

    identity["provision"] = provision
    request = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    with pytest.raises(ClassroomError):
        add_students(request, section.pk, {"students": rows})
    assert IdempotencyRecord.objects.get().status == "PREPARED"
    with pytest.raises(ClassroomError) as conflict:
        add_students(request, section.pk, {"students": student_rows(2)})
    assert conflict.value.status_code == 422 and len(calls) == 1
    assert add_students(request, section.pk, {"students": rows}).status_code == 200
    assert calls[0] == calls[1]


def test_permission_revoked_during_remote_call_keeps_prepared_without_enrollment(
    section, actors, identity, command_request
):
    user_id = uuid4()

    def provision(rows, key):
        assert not connection.in_atomic_block
        ClassTeacher.objects.filter(class_section=section).update(
            status="LEFT", left_at=timezone.now()
        )
        return provision_result(rows, [user_id])

    identity["provision"] = provision
    request = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    with pytest.raises(ClassroomError) as error:
        add_students(request, section.pk, {"students": student_rows()})
    assert error.value.status_code == 404
    assert not Enrollment.objects.filter(user_id=user_id).exists()
    assert IdempotencyRecord.objects.get().status == "PREPARED"


def test_final_database_failure_rolls_back_entire_batch_but_keeps_prepared(
    section, actors, identity, command_request, monkeypatch
):
    ids = [uuid4(), uuid4()]
    identity["provision"] = lambda rows, key: provision_result(rows, ids)

    def fail(*args, **kwargs):
        raise DatabaseError("isolated test failure")

    monkeypatch.setattr("apps.courses.services.enrollments.record_activity", fail)
    request = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    with pytest.raises(DatabaseError):
        add_students(request, section.pk, {"students": student_rows(2)})
    assert not Enrollment.objects.filter(user_id__in=ids).exists()
    assert IdempotencyRecord.objects.get().status == "PREPARED"
    assert not Activity.objects.exists()


def test_repeated_and_inactive_student_results_are_explicit(
    section, actors, identity, command_request
):
    inactive_id = uuid4()
    Enrollment.objects.create(
        class_section=section, user_id=inactive_id, status="REMOVED", left_at=timezone.now()
    )
    identity["provision"] = lambda rows, key: provision_result(
        rows, [actors["member"], actors["member"], inactive_id]
    )
    response = add_students(
        command_request(actors["teacher"], "/students/", roles=("TEACHER",)),
        section.pk,
        {"students": student_rows(3)},
    )
    results = response.data["data"]["results"]
    assert [row["enrollment_result"] for row in results] == ["ALREADY_ENROLLED", "FAILED", "FAILED"]
    assert results[1]["reason"] == "DUPLICATE_STUDENT"
    assert results[2]["reason"] == "ENROLLMENT_INACTIVE"


def test_input_duplicates_are_skipped_before_remote_call_and_original_order_is_preserved(
    section, actors, identity, command_request
):
    rows = [
        {"row_number": 1, "email": " One@Example.test ", "student_id": "ST1"},
        {"row_number": 2, "email": "one@example.test", "student_id": "ST2"},
        {"row_number": 3, "student_id": " st1 "},
        {"row_number": 4, "student_id": "ST4"},
    ]
    ids = [uuid4(), uuid4()]

    def provision(received, key):
        assert not connection.in_atomic_block
        assert received == [rows[0], rows[3]]
        return {
            "results": [
                {
                    **row,
                    "user_id": str(pk),
                    "account_result": result,
                    "account_status": "ACTIVE",
                    "reason": None,
                }
                for row, pk, result in zip(received, ids, ["CREATED", "EXISTING"], strict=True)
            ]
        }

    identity["provision"] = provision
    request = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    response = add_students(request, section.pk, {"students": rows})
    assert [row["row_number"] for row in response.data["data"]["results"]] == [1, 2, 3, 4]
    assert [row["account_result"] for row in response.data["data"]["results"]] == [
        "CREATED",
        "NOT_REQUESTED",
        "NOT_REQUESTED",
        "EXISTING",
    ]
    summary = response.data["data"]["summary"]
    assert (
        summary["duplicates"] == 2
        and summary["created_accounts"] == summary["existing_accounts"] == 1
    )
    assert summary["enrolled"] == 2 and summary["failed"] == 2
    assert add_students(request, section.pk, {"students": rows}).data == response.data
    assert len([call for call in identity["calls"] if call[0] == "provision"]) == 1


def test_duplicate_subset_and_key_are_stable_after_timeout(
    section, actors, identity, command_request
):
    rows = [
        {"row_number": 1, "email": "one@example.test"},
        {"row_number": 2, "email": "ONE@example.test"},
    ]
    calls = []

    def provision(received, key):
        calls.append((received, key))
        if len(calls) == 1:
            raise ClassroomError("IDENTITY_UNAVAILABLE", "Chưa thể xác minh tài khoản.", 503)
        return {
            "results": [{**received[0], "account_result": "FLAGGED", "reason": "STUDENT_CONFLICT"}]
        }

    identity["provision"] = provision
    request = command_request(actors["teacher"], "/students/", roles=("TEACHER",))
    with pytest.raises(ClassroomError):
        add_students(request, section.pk, {"students": rows})
    assert IdempotencyRecord.objects.get().status == "PREPARED"
    response = add_students(request, section.pk, {"students": rows})
    assert calls[0] == calls[1] and calls[0][0] == [rows[0]]
    assert response.data["data"]["summary"]["flagged"] == 1
    assert response.data["data"]["summary"]["duplicates"] == 1
