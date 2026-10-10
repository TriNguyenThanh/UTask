from functools import partial
from uuid import uuid4

import pytest
from allauth.account.models import EmailConfirmation
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountStatus, AuditLog, IdempotencyRecord, OutboxEvent, User
from tests.helpers import PASSWORD, create_user, login, mail_secret, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]
URL = "/api/v1/internal/users/provision-students"


@pytest.fixture
def teacher_session(settings, db):
    settings.IDENTITY_SERVICE_KEYS = {"classroom": "test-classroom", "work": "test-work"}
    client = APIClient()
    user = create_user(global_role_code="TEACHER")
    response = login(client, user)
    return client, response.json()["data"]["access"]


@pytest.fixture
def teacher_client(teacher_session):
    return teacher_session[0]


def provision(client, rows, key=None):
    return client.post(
        URL,
        {"students": rows},
        format="json",
        HTTP_X_SERVICE_KEY="test-classroom",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def row(email="new-student@example.edu.vn", student_id=" sv001 "):
    return {
        "row_number": 2,
        "email": email,
        "student_id": student_id,
        "first_name": "An",
        "last_name": "Nguyễn",
    }


def test_provision_activation_replay_and_payload_conflict(teacher_client):
    key = str(uuid4())
    result = provision(teacher_client, [row()], key)
    assert result.status_code == 201, result.json()
    data = result.json()["data"]
    assert data["summary"] == {
        "total_records": 1,
        "created_accounts": 1,
        "existing_accounts": 0,
        "flagged_records": 0,
        "failed_records": 0,
    }
    user = User.objects.get(pk=data["results"][0]["user_id"])
    assert user.student_id == "SV001"
    assert not user.has_usable_password()
    assert user.account_status == AccountStatus.PENDING_ACTIVATION
    event = OutboxEvent.objects.get(aggregate_id=user.pk, event_type="identity.student.imported")
    assert OutboxEvent.objects.filter(aggregate_id=user.pk).count() == 2
    secret = mail_secret(event)
    assert secret["key"] != EmailConfirmation.objects.get(email_address__user=user).key
    receipt = IdempotencyRecord.objects.get()
    assert receipt.response_body == result.json()
    assert secret["key"] not in str(receipt.response_body)
    replay = provision(teacher_client, [row()], key)
    assert replay.status_code == 201 and replay.json() == result.json()
    assert OutboxEvent.objects.filter(aggregate_id=user.pk).count() == 2
    assert provision(teacher_client, [row(email="other@example.edu.vn")], key).status_code == 422
    public = APIClient()
    assert (
        public.post(
            "/activate",
            {"key": secret["key"], "new_password1": PASSWORD, "new_password2": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    login(public, user)
    assert public.get("/users/me").status_code == 200


def test_provision_existing_identity_rules_and_invalid_rows(teacher_client):
    existing = create_user()
    other = create_user(student_id="OTHER")
    teacher = create_user(global_role_code="TEACHER")
    deleted = create_user(deleted_at=timezone.now())
    result = provision(
        teacher_client,
        [
            row(existing.email, "ASSIGNED"),
            row(existing.email, "OTHER"),
            row(teacher.email, None),
            row(deleted.email, None),
            row("bad-email", None),
            {"row_number": 8, "student_id": "UNKNOWN"},
            row("", "OTHER"),
        ],
    )
    assert result.status_code == 200, result.json()
    rows = result.json()["data"]["results"]
    assert rows[0]["account_result"] == "EXISTING"
    assert rows[1]["reason"] == "IDENTITY_CONFLICT"
    assert rows[2]["reason"] == "FLAGGED_ROLE_CONFLICT"
    assert rows[3]["reason"] == "ACCOUNT_UNAVAILABLE"
    assert rows[4]["reason"] == "VALIDATION_ERROR"
    assert rows[5]["reason"] == "STUDENT_ID_NOT_FOUND"
    assert rows[6]["user_id"] == str(other.pk)
    existing.refresh_from_db()
    assert existing.student_id == "ASSIGNED"
    assert OutboxEvent.objects.filter(event_type="identity.user.updated").count() == 1


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("missing-service-key", 403, "SERVICE_ACCESS_DENIED"),
        ("missing-idempotency-key", 400, "IDEMPOTENCY_KEY_REQUIRED"),
        ("invalid-idempotency-key", 400, "VALIDATION_ERROR"),
        ("student-actor", 403, "FORBIDDEN_TEACHER_OR_ADMIN"),
    ],
)
def test_provision_key_and_delegated_permissions(teacher_client, case, status, code):
    headers = {"HTTP_X_SERVICE_KEY": "test-classroom", "HTTP_IDEMPOTENCY_KEY": str(uuid4())}
    if case == "missing-service-key":
        headers.pop("HTTP_X_SERVICE_KEY")
    elif case == "missing-idempotency-key":
        headers.pop("HTTP_IDEMPOTENCY_KEY")
    elif case == "invalid-idempotency-key":
        headers["HTTP_IDEMPOTENCY_KEY"] = "bad-key"
    else:
        login(teacher_client, create_user())
    result = teacher_client.post(URL, {"students": [row()]}, format="json", **headers)

    assert result.status_code == status
    assert result.json()["error"]["code"] == code
    assert not IdempotencyRecord.objects.exists()
    assert not User.objects.filter(email=row()["email"]).exists()
    assert not OutboxEvent.objects.exists()


def test_resend_import_activation_invalidates_old_key_and_active_guard(teacher_client):
    result = provision(teacher_client, [row()])
    user_id = result.json()["data"]["results"][0]["user_id"]
    user = User.objects.get(pk=user_id)
    old = mail_secret(OutboxEvent.objects.get(event_type="identity.student.imported"))["key"]
    url = f"/api/v1/internal/users/{user_id}/resend-activation"
    assert (
        teacher_client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="test-classroom").status_code
        == 200
    )
    new = mail_secret(OutboxEvent.objects.get(event_type="identity.activation.requested"))["key"]
    assert old != new
    client = APIClient()
    assert client.post("/activate", {"key": old}, format="json").status_code == 404
    assert (
        client.post(
            "/activate",
            {"key": new, "new_password1": PASSWORD, "new_password2": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    assert (
        teacher_client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="test-classroom").json()[
            "error"
        ]["code"]
        == "ACCOUNT_ALREADY_ACTIVE"
    )
    user.refresh_from_db()
    assert user.is_active


def test_provision_rollback_when_mail_key_missing(teacher_client, settings):
    settings.IDENTITY_MAIL_KEY = None
    result = provision(teacher_client, [row()])
    assert result.status_code == 503
    assert not User.objects.filter(email=row()["email"]).exists()
    assert not IdempotencyRecord.objects.exists()
    assert not OutboxEvent.objects.exists()
    assert not AuditLog.objects.filter(action="STUDENT_IMPORTED").exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False], ids=["same-key", "different-keys"])
def test_provision_concurrent_requests_create_one_account(teacher_session, same_key):
    _, access = teacher_session
    keys = [str(uuid4()), str(uuid4())]
    if same_key:
        keys[1] = keys[0]

    def worker(key):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + access)
        result = provision(client, [row()], key)
        return result.status_code, result.json()

    results = run_concurrent(*(partial(worker, key) for key in keys))
    assert sorted(status for status, _ in results) == ([201, 201] if same_key else [200, 201])
    assert len({body["data"]["results"][0]["user_id"] for _, body in results}) == 1
    assert User.objects.filter(email=row()["email"]).count() == 1
    assert OutboxEvent.objects.filter(event_type="identity.student.imported").count() == 1
    assert IdempotencyRecord.objects.count() == (1 if same_key else 2)
