"""Tests for mail crypto, outbox immutability, idempotency receipts, drain, and retention."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.accounts.models import (
    AccountStatus,
    AuditLog,
    EmailChangeRequest,
    GlobalRole,
    GlobalRoleCode,
    User,
    UserSession,
)
from apps.accounts.roles import ROLE_SEEDS
from apps.messaging.models import (
    IdempotencyRecord,
    IdempotencyStatus,
    OutboxEvent,
    OutboxProducer,
)
from apps.messaging.services.mail_crypto import (
    encrypt_mail_payload,
    mail_key,
    redact_expired_mail_secret,
)
from apps.messaging.services.maintenance import cleanup_core_data
from apps.messaging.services.outbox import (
    emit_identity_event,
    emit_identity_mail,
    emit_work_event,
    emit_work_events,
)
from apps.messaging.services.publisher import drain_outbox
from apps.messaging.services.receipts import (
    begin_receipt,
    claim_receipt,
    finish_receipt,
    lookup_receipt,
    receipt_scope,
    replay_response,
    require_key,
    save_receipt,
)
from apps.projects.models import Project
from common.errors import CoreAPIError


def _ensure_roles() -> None:
    for code, name, description in ROLE_SEEDS:
        GlobalRole.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )


def _create_user(*, student_id: str | None = None) -> User:
    _ensure_roles()
    suffix = uuid4().hex[:8]
    return User.objects.create_user(
        email=f"msg_{suffix}@example.edu.vn",
        username=f"msg_{suffix}",
        password="StrongPass123!",
        student_id=student_id,
        first_name="Minh",
        last_name="Tran",
        global_role_code=GlobalRoleCode.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )


def _create_project() -> Project:
    suffix = uuid4().hex[:6].upper()
    return Project.objects.create(
        identifier=f"PRJ{suffix[:5]}",
        name=f"Project {suffix}",
        classroom_group_id=str(uuid4()),
    )


def _make_request(user: User, path: str, *, key: str | None = None, method: str = "POST"):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key is not None else {}
    factory = APIRequestFactory()
    request = getattr(factory, method.lower())(path, {}, format="json", **headers)
    request.user = user
    return request


# ---------------------------------------------------------------------------
# 1. Mail AES-256-GCM encryption & expiration redaction (pure unit tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mail_crypto_roundtrip_and_tamper_rejection(settings):
    key = mail_key()
    assert len(key) == 32

    event_id = uuid4()
    user_id = uuid4()
    event_type = "identity.activation.requested"
    expires = (timezone.now() + timedelta(hours=1)).isoformat()
    secret = {"key": "secret-activation-token", "attempts": 1}

    encrypted = encrypt_mail_payload(key, event_id, event_type, user_id, expires, secret)
    assert encrypted["key_id"] == settings.IDENTITY_MAIL_KEY_ID
    assert encrypted["expires_at"] == expires

    nonce = base64.b64decode(encrypted["nonce"])
    ciphertext = base64.b64decode(encrypted["ciphertext"])
    aad = json.dumps(
        [str(event_id), event_type, str(user_id), expires], separators=(",", ":")
    ).encode()

    decrypted = json.loads(AESGCM(key).decrypt(nonce, ciphertext, aad).decode())
    assert decrypted == secret

    tampered_ct = bytearray(ciphertext)
    tampered_ct[0] ^= 0xFF
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(nonce, bytes(tampered_ct), aad)

    tampered_nonce = bytearray(nonce)
    tampered_nonce[0] ^= 0x01
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(bytes(tampered_nonce), ciphertext, aad)

    wrong_aad = json.dumps(
        [str(event_id), event_type, str(uuid4()), expires], separators=(",", ":")
    ).encode()
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(nonce, ciphertext, wrong_aad)

    with pytest.raises(InvalidTag):
        AESGCM(b"z" * 32).decrypt(nonce, ciphertext, aad)


@pytest.mark.unit
def test_mail_key_invalid_configuration_raises_503(settings):
    settings.IDENTITY_MAIL_KEY = "not-base64!!!"
    with pytest.raises(CoreAPIError) as exc_info:
        mail_key()
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "IDENTITY_UNAVAILABLE"

    settings.IDENTITY_MAIL_KEY = base64.b64encode(b"short-key").decode()
    with pytest.raises(CoreAPIError) as exc_info:
        mail_key()
    assert exc_info.value.status_code == 503

    settings.IDENTITY_MAIL_KEY = base64.b64encode(b"0" * 32).decode()
    settings.IDENTITY_MAIL_KEY_ID = ""
    with pytest.raises(CoreAPIError) as exc_info:
        mail_key()
    assert exc_info.value.status_code == 503


@pytest.mark.unit
def test_redact_expired_mail_secret_only_redacts_when_expired():
    now = timezone.now()
    future_env = {
        "event_id": str(uuid4()),
        "data": {"secret": {"expires_at": (now + timedelta(minutes=5)).isoformat(), "c": "x"}},
    }
    unchanged, changed = redact_expired_mail_secret(future_env, now)
    assert changed is False
    assert unchanged["data"]["secret"] is not None

    expired_env = {
        "event_id": str(uuid4()),
        "data": {
            "email": "student@example.edu.vn",
            "secret": {"expires_at": (now - timedelta(seconds=1)).isoformat(), "c": "x"},
        },
    }
    redacted, changed = redact_expired_mail_secret(expired_env, now)
    assert changed is True
    assert redacted["data"]["secret"] is None
    assert redacted["data"]["email"] == "student@example.edu.vn"
    # Original dictionary must remain unmutated.
    assert expired_env["data"]["secret"] is not None

    already_redacted, changed_again = redact_expired_mail_secret(redacted, now)
    assert changed_again is False
    assert already_redacted["data"]["secret"] is None


# ---------------------------------------------------------------------------
# 2. core_outbox_events constraints & core_outbox_immutable PostgreSQL trigger
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.postgres
def test_outbox_emit_helpers_and_immutability_trigger(db):
    user = _create_user(student_id="SV202601")
    project = _create_project()

    id_event = emit_identity_event(user, "identity.user.updated", {"user_id": str(user.pk)})
    assert id_event.producer == OutboxProducer.IDENTITY
    assert id_event.topic == "utask.identity.events"
    assert id_event.partition_key == str(user.pk)
    assert id_event.stream_sequence is None
    assert id_event.data["producer"] == "identity-service"

    mail_event = emit_identity_mail(
        user,
        "identity.student.imported",
        {"key": "import-token-123"},
        lifetime=3600,
    )
    assert mail_event.producer == OutboxProducer.IDENTITY
    assert mail_event.topic == "utask.identity.events"
    assert mail_event.data["data"]["student_id"] == "SV202601"
    assert isinstance(mail_event.data["data"]["secret"], dict)
    assert "ciphertext" in mail_event.data["data"]["secret"]

    # emit_work_event / emit_work_events inside transaction atomically assign stream_sequence.
    with transaction.atomic():
        first = emit_work_event(
            project,
            "work.project.updated",
            {"name": project.name},
            aggregate_type="project",
            aggregate_id=project.pk,
        )
        batch = emit_work_events(
            project,
            [
                {"event_type": "work.task.created", "aggregate_type": "task", "data": {"n": 1}},
                {"event_type": "work.task.updated", "aggregate_type": "task", "data": {"n": 2}},
            ],
        )

    assert first.producer == OutboxProducer.WORK
    assert first.topic == "utask.work.events"
    assert first.partition_key == str(project.pk)
    assert [first.stream_sequence, batch[0].stream_sequence, batch[1].stream_sequence] == [1, 2, 3]
    assert first.data["producer"] == "work-service"
    assert first.data["project_sequence"] == 1
    assert batch[1].data["project_sequence"] == 3

    # Trigger blocks updating immutable envelope columns.
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            OutboxEvent.objects.filter(pk=id_event.pk).update(event_type="identity.user.tampered")
    assert getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_outbox_immutable"
    )

    # Trigger blocks mutating work-service payload completely.
    tampered_work = {**first.data, "data": {"name": "Tampered"}}
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            OutboxEvent.objects.filter(pk=first.pk).update(data=tampered_work)
    assert getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_outbox_immutable"
    )

    # Trigger blocks mutating non-secret fields or replacing secret with non-null on identity event.
    bad_identity_data = {**mail_event.data, "data": {**mail_event.data["data"], "email": "x@y.vn"}}
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            OutboxEvent.objects.filter(pk=mail_event.pk).update(data=bad_identity_data)
    assert getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_outbox_immutable"
    )

    non_null_secret = {
        **mail_event.data,
        "data": {**mail_event.data["data"], "secret": {"key_id": "forged"}},
    }
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            OutboxEvent.objects.filter(pk=mail_event.pk).update(data=non_null_secret)
    assert getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_outbox_immutable"
    )

    # Trigger ALLOWS redacting data.data.secret -> null on identity-service event.
    redacted_data = {**mail_event.data, "data": {**mail_event.data["data"], "secret": None}}
    OutboxEvent.objects.filter(pk=mail_event.pk).update(data=redacted_data)
    mail_event.refresh_from_db()
    assert mail_event.data["data"]["secret"] is None

    # Trigger rejects INSERT with mismatched envelope metadata.
    bad_id = uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            OutboxEvent.objects.create(
                id=bad_id,
                topic="utask.identity.events",
                producer=OutboxProducer.IDENTITY,
                partition_key=str(user.pk),
                aggregate_type="user",
                aggregate_id=str(user.pk),
                event_type="identity.user.updated",
                event_version=1,
                data={
                    "event_id": str(bad_id),
                    "event_type": "identity.user.updated",
                    "event_version": 1,
                    "aggregate_id": str(user.pk),
                    "producer": "wrong-producer",
                    "data": {},
                },
            )
    assert getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_outbox_envelope"
    )


@pytest.mark.integration
def test_emit_work_events_requires_atomic_transaction(transactional_db):
    project = _create_project()
    with pytest.raises(RuntimeError, match="atomic|Outbox must commit"):
        emit_work_event(project, "work.project.updated", {"name": "fail"})


# ---------------------------------------------------------------------------
# 3. core_idempotency_records & core_receipt_immutable PostgreSQL trigger
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.postgres
def test_idempotency_receipts_replay_conflict_and_immutability_trigger(db):
    user = _create_user()
    req_no_key = _make_request(user, "/api/classroom/courses/")
    with pytest.raises(CoreAPIError) as missing_exc:
        require_key(req_no_key, require_uuid=True)
    assert missing_exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"

    req_bad_uuid = _make_request(user, "/api/classroom/courses/", key="not-a-uuid")
    with pytest.raises(CoreAPIError) as bad_uuid_exc:
        require_key(req_bad_uuid, require_uuid=True)
    assert bad_uuid_exc.value.code == "VALIDATION_ERROR"

    # begin_receipt + finish_receipt + replay + 422 payload mismatch.
    key1 = str(uuid4())
    req1 = _make_request(user, "/api/classroom/courses/", key=key1)
    payload_a = {"code": "SE101", "name": "Software Engineering"}
    with transaction.atomic():
        receipt = begin_receipt(req1, payload_a, domain="classroom", require_uuid=True)
        assert receipt.status == IdempotencyStatus.PREPARED
        resp = finish_receipt(receipt, {"id": "course-1"}, status=201, message="Đã tạo môn học.")
    assert resp.status_code == 201
    assert resp.data["success"] is True
    assert resp.data["data"] == {"id": "course-1"}

    # Replaying identical key + payload returns cached response.
    with transaction.atomic():
        replayed_receipt = begin_receipt(req1, payload_a, domain="classroom", require_uuid=True)
        assert replayed_receipt.status == IdempotencyStatus.COMPLETED
        replayed = replay_response(replayed_receipt)
    assert replayed.status_code == 201
    assert replayed.data == resp.data

    # Reusing key with different payload raises 422 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD.
    scope1 = receipt_scope(req1, key1, domain="classroom")
    with pytest.raises(CoreAPIError) as conflict_exc:
        lookup_receipt(scope1, {"code": "SE102", "name": "Different"})
    assert conflict_exc.value.status_code == 422
    assert conflict_exc.value.code == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"

    # claim_receipt + save_receipt flow & in-flight 409 conflict.
    key2 = str(uuid4())
    req2 = _make_request(user, "/api/work/projects/", key=key2)
    scope2 = receipt_scope(req2, key2, domain="work")
    payload_b = {"name": "Capstone"}
    with transaction.atomic():
        claimed, fresh = claim_receipt(scope2, payload_b, domain="work")
        assert fresh is True
        assert claimed.status == IdempotencyStatus.PREPARED

        with pytest.raises(CoreAPIError) as inflight_exc:
            claim_receipt(scope2, payload_b, domain="work")
        assert inflight_exc.value.status_code == 409
        assert inflight_exc.value.code == "CONCURRENT_MUTATION_IN_PROGRESS"

        saved_resp = save_receipt(
            scope2, payload_b, {"project": "p1"}, status=201, message="Đã tạo dự án."
        )
        assert saved_resp.status_code == 201

        reclaimed, fresh_again = claim_receipt(scope2, payload_b, domain="work")
        assert fresh_again is False
        assert reclaimed.pk == claimed.pk

        cached_via_save = save_receipt(
            scope2, payload_b, {"project": "ignored"}, status=200, message="Ignored"
        )
        assert cached_via_save.status_code == 201
        assert cached_via_save.data["data"] == {"project": "p1"}

    # Trigger core_receipt_immutable blocks mutating a COMPLETED receipt.
    with pytest.raises(IntegrityError) as immut_exc:
        with transaction.atomic():
            IdempotencyRecord.objects.filter(pk=receipt.pk).update(response_status=200)
    assert getattr(getattr(immut_exc.value.__cause__, "diag", None), "constraint_name", None) == (
        "chk_core_receipt_immutable"
    )

    with pytest.raises(IntegrityError) as body_immut_exc:
        with transaction.atomic():
            IdempotencyRecord.objects.filter(pk=receipt.pk).update(
                response_body={**resp.data, "message": "Mutated"}
            )
    assert (
        getattr(getattr(body_immut_exc.value.__cause__, "diag", None), "constraint_name", None)
        == "chk_core_receipt_immutable"
    )

    # Trigger rejects completing a receipt without a valid 5-key success envelope.
    with pytest.raises(IntegrityError) as incomplete_exc:
        with transaction.atomic():
            IdempotencyRecord.objects.create(
                domain="work",
                actor_user_id=str(user.pk),
                http_method="POST",
                endpoint_path="/api/work/invalid/",
                idempotency_key=str(uuid4()),
                payload_hash="a" * 64,
                status=IdempotencyStatus.COMPLETED,
                response_status=200,
                response_body={"only_one_key": True},
            )
    assert (
        getattr(getattr(incomplete_exc.value.__cause__, "diag", None), "constraint_name", None)
        == "chk_core_receipt_complete"
    )


# ---------------------------------------------------------------------------
# 4. drain_outbox with fake Kafka publisher (strict ordering, redaction, retry)
# ---------------------------------------------------------------------------


class _FakeKafkaPublisher:
    def __init__(self, *, fail_event_ids: set | None = None):
        self.published: list[tuple[str, str, str, int | None, dict]] = []
        self.fail_event_ids = fail_event_ids or set()

    def publish(self, event: OutboxEvent) -> None:
        if event.id in self.fail_event_ids:
            raise ConnectionError("broker unavailable")
        self.published.append(
            (
                event.topic,
                event.producer,
                event.partition_key,
                event.stream_sequence,
                json.loads(json.dumps(event.data)),
            )
        )


@pytest.mark.integration
@pytest.mark.postgres
def test_drain_outbox_strict_work_ordering_producer_envelope_and_secret_redaction(
    transactional_db,
):
    user = _create_user(student_id="SV202699")
    project = _create_project()

    # Must refuse to run inside an atomic transaction.
    with transaction.atomic():
        with pytest.raises(RuntimeError, match="cannot run inside a business transaction"):
            drain_outbox(publisher=_FakeKafkaPublisher())

    now = timezone.now()
    # Emit work events 1, 2, 3; deliberately give sequence 3 an EARLIER created_at than 1 & 2
    # to prove drain_outbox orders strictly by stream_sequence per work partition.
    with transaction.atomic():
        ev1, ev2, ev3 = emit_work_events(
            project,
            [
                {"event_type": "work.task.created", "aggregate_type": "task", "data": {"seq": 1}},
                {"event_type": "work.task.updated", "aggregate_type": "task", "data": {"seq": 2}},
                {"event_type": "work.task.moved", "aggregate_type": "task", "data": {"seq": 3}},
            ],
        )

    # Insert an already-expired identity mail event (lifetime=-60 seconds) and a fresh one.
    expired_mail = emit_identity_mail(
        user,
        "identity.activation.requested",
        {"key": "expired-secret"},
        lifetime=-60,
    )
    active_mail = emit_identity_mail(
        user,
        "identity.password_reset.requested",
        {"token": "live-secret", "uid": "u1"},
        lifetime=900,
    )
    # Create an out-of-order created_at work event directly via model on a second project to prove
    # stream_sequence takes precedence over created_at.
    project2 = _create_project()
    with transaction.atomic():
        p2_ev2_id = uuid4()
        p2_ev1_id = uuid4()
        OutboxEvent.objects.create(
            id=p2_ev2_id,
            topic="utask.work.events",
            producer=OutboxProducer.WORK,
            partition_key=str(project2.pk),
            stream_sequence=2,
            aggregate_type="task",
            aggregate_id=str(project2.pk),
            event_type="work.task.updated",
            event_version=1,
            created_at=now - timedelta(minutes=10),
            data={
                "event_id": str(p2_ev2_id),
                "event_type": "work.task.updated",
                "event_version": 1,
                "aggregate_id": str(project2.pk),
                "producer": OutboxProducer.WORK,
                "project_id": str(project2.pk),
                "project_sequence": 2,
                "entity_version": 2,
                "data": {"seq": 2},
            },
        )
        OutboxEvent.objects.create(
            id=p2_ev1_id,
            topic="utask.work.events",
            producer=OutboxProducer.WORK,
            partition_key=str(project2.pk),
            stream_sequence=1,
            aggregate_type="task",
            aggregate_id=str(project2.pk),
            event_type="work.task.created",
            event_version=1,
            created_at=now - timedelta(minutes=1),
            data={
                "event_id": str(p2_ev1_id),
                "event_type": "work.task.created",
                "event_version": 1,
                "aggregate_id": str(project2.pk),
                "producer": OutboxProducer.WORK,
                "project_id": str(project2.pk),
                "project_sequence": 1,
                "entity_version": 1,
                "data": {"seq": 1},
            },
        )

    fake = _FakeKafkaPublisher()
    published_count = drain_outbox(publisher=fake, batch_size=20, time_budget=10)
    assert published_count == 7

    # Verify strict stream_sequence ordering per project partition.
    p1_seqs = [
        seq for _t, prod, key, seq, _env in fake.published if key == str(project.pk) and prod
    ]
    assert p1_seqs == [1, 2, 3]
    p2_seqs = [seq for _t, _prod, key, seq, _env in fake.published if key == str(project2.pk)]
    assert p2_seqs == [1, 2]

    # Verify producer envelope preservation & expired mail secret redaction before publish.
    by_event_id = {
        env["event_id"]: (topic, prod, env) for topic, prod, _k, _s, env in fake.published
    }
    assert by_event_id[str(ev1.pk)][0] == "utask.work.events"
    assert by_event_id[str(ev1.pk)][1] == "work-service"
    assert by_event_id[str(ev1.pk)][2]["producer"] == "work-service"

    expired_topic, expired_prod, expired_payload = by_event_id[str(expired_mail.pk)]
    assert expired_topic == "utask.identity.events"
    assert expired_prod == "identity-service"
    assert expired_payload["producer"] == "identity-service"
    assert expired_payload["data"]["secret"] is None

    _, _, active_payload = by_event_id[str(active_mail.pk)]
    assert isinstance(active_payload["data"]["secret"], dict)

    # All events marked published_at in DB and expired secret persisted as null.
    for event in (ev1, ev2, ev3, expired_mail, active_mail):
        event.refresh_from_db()
        assert event.published_at is not None
        assert event.last_error is None
        assert event.next_attempt_at is None
    assert expired_mail.data["data"]["secret"] is None


@pytest.mark.integration
def test_drain_outbox_retry_and_head_of_line_partition_blocking(transactional_db):
    project = _create_project()
    with transaction.atomic():
        ev1, ev2 = emit_work_events(
            project,
            [
                {"event_type": "work.task.created", "aggregate_type": "task", "data": {"n": 1}},
                {"event_type": "work.task.updated", "aggregate_type": "task", "data": {"n": 2}},
            ],
        )

    failing = _FakeKafkaPublisher(fail_event_ids={ev1.pk})
    count = drain_outbox(publisher=failing, batch_size=10, time_budget=5)
    assert count == 0
    assert failing.published == []

    ev1.refresh_from_db()
    ev2.refresh_from_db()
    assert ev1.published_at is None
    assert ev1.retry_count == 1
    assert ev1.last_error == "ConnectionError"
    assert ev1.next_attempt_at is not None and ev1.next_attempt_at > timezone.now()
    # Event 2 must stay unpublished behind failed event 1 in the same partition.
    assert ev2.published_at is None
    assert ev2.retry_count == 0


# ---------------------------------------------------------------------------
# 5. cleanup_core_data retention maintenance
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.postgres
def test_cleanup_core_data_purges_old_technical_rows_and_preserves_pending_and_audit(
    transactional_db, settings
):
    now = timezone.now()
    user = _create_user(student_id="SV202655")

    # Old published outbox (eligible for deletion).
    old_published = emit_identity_event(user, "identity.user.updated", {"v": 1})
    OutboxEvent.objects.filter(pk=old_published.pk).update(
        published_at=now - timedelta(days=settings.IDENTITY_OUTBOX_RETENTION_DAYS + 2)
    )

    # Recent published outbox (must be kept).
    recent_published = emit_identity_event(user, "identity.user.updated", {"v": 2})
    OutboxEvent.objects.filter(pk=recent_published.pk).update(published_at=now - timedelta(hours=1))

    # Very old UNPUBLISHED outbox (MUST NEVER be deleted).
    old_unpublished_id = uuid4()
    old_unpublished = OutboxEvent.objects.create(
        id=old_unpublished_id,
        topic="utask.identity.events",
        producer=OutboxProducer.IDENTITY,
        partition_key=str(user.pk),
        aggregate_type="user",
        aggregate_id=str(user.pk),
        event_type="identity.user.created",
        event_version=1,
        created_at=now - timedelta(days=90),
        data={
            "event_id": str(old_unpublished_id),
            "event_type": "identity.user.created",
            "event_version": 1,
            "aggregate_id": str(user.pk),
            "producer": OutboxProducer.IDENTITY,
            "data": {"user_id": str(user.pk)},
        },
    )

    # Expired mail event (secret should be redacted by cleanup_core_data, row kept if unpublished).
    expired_mail = emit_identity_mail(
        user,
        "identity.student.imported",
        {"key": "old-secret-to-redact"},
        lifetime=-300,
    )

    # Expired receipt (eligible) vs active receipt (must be kept).
    expired_receipt = IdempotencyRecord.objects.create(
        domain="classroom",
        actor_user_id=str(user.pk),
        http_method="POST",
        endpoint_path="/api/classroom/courses/",
        idempotency_key=str(uuid4()),
        payload_hash="1" * 64,
        status=IdempotencyStatus.PREPARED,
        created_at=now - timedelta(days=3),
        expires_at=now - timedelta(hours=1),
    )
    old_no_expiry_receipt = IdempotencyRecord.objects.create(
        domain="identity",
        actor_user_id=str(user.pk),
        http_method="POST",
        endpoint_path="/api/v1/internal/users/provision-students",
        idempotency_key=str(uuid4()),
        payload_hash="2" * 64,
        status=IdempotencyStatus.PREPARED,
        created_at=now - timedelta(days=settings.IDENTITY_RECEIPT_RETENTION_DAYS + 2),
        expires_at=None,
    )
    active_receipt = IdempotencyRecord.objects.create(
        domain="work",
        actor_user_id=str(user.pk),
        http_method="POST",
        endpoint_path="/api/work/projects/",
        idempotency_key=str(uuid4()),
        payload_hash="3" * 64,
        status=IdempotencyStatus.PREPARED,
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=23),
    )

    # Old expired session & email change request.
    old_session = UserSession.objects.create(
        user=user,
        token_family=uuid4(),
        refresh_token_hash=hashlib.sha256(b"old-sess").hexdigest(),
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=now + timedelta(hours=1),
    )
    UserSession.objects.filter(pk=old_session.pk).update(
        created_at=now - timedelta(days=settings.IDENTITY_SESSION_RETENTION_DAYS + 10),
        expires_at=now - timedelta(days=settings.IDENTITY_SESSION_RETENTION_DAYS + 5),
    )
    expired_email_req = EmailChangeRequest.objects.create(
        user=user,
        new_email="new_email@example.edu.vn",
        token_hash=hashlib.sha256(b"tok").hexdigest(),
        expires_at=now + timedelta(hours=1),
    )
    EmailChangeRequest.objects.filter(pk=expired_email_req.pk).update(
        created_at=now - timedelta(days=5),
        expires_at=now - timedelta(hours=2),
    )

    # AuditLog record MUST NEVER be purged.
    audit_log = AuditLog.objects.create(
        actor_id=str(user.pk),
        action="LOGIN_SUCCESS",
        target_user_id=str(user.pk),
        ip_address="127.0.0.1",
        user_agent="pytest",
        details={"source": "retention-test"},
    )

    # Dry run must count without deleting or redacting.
    dry_result = cleanup_core_data(apply=False, now=now)
    assert dry_result["published_outbox"] >= 1
    assert dry_result["receipts"] >= 2
    assert dry_result["sessions"] >= 1
    assert dry_result["email_change_requests"] >= 1
    assert dry_result["expired_mail_secrets"] >= 1
    assert OutboxEvent.objects.filter(pk=old_published.pk).exists()
    assert IdempotencyRecord.objects.filter(pk=expired_receipt.pk).exists()
    expired_mail.refresh_from_db()
    assert expired_mail.data["data"]["secret"] is not None

    # Apply run purges expired/old technical rows, redacts mail secret, keeps pending & AuditLog.
    applied = cleanup_core_data(apply=True, now=now)
    assert applied["published_outbox"] >= 1
    assert applied["receipts"] >= 2
    assert applied["expired_mail_secrets"] >= 1

    assert not OutboxEvent.objects.filter(pk=old_published.pk).exists()
    assert OutboxEvent.objects.filter(pk=recent_published.pk).exists()
    assert OutboxEvent.objects.filter(pk=old_unpublished.pk).exists()

    expired_mail.refresh_from_db()
    assert expired_mail.data["data"]["secret"] is None

    assert not IdempotencyRecord.objects.filter(pk=expired_receipt.pk).exists()
    assert not IdempotencyRecord.objects.filter(pk=old_no_expiry_receipt.pk).exists()
    assert IdempotencyRecord.objects.filter(pk=active_receipt.pk).exists()

    assert not UserSession.objects.filter(pk=old_session.pk).exists()
    assert not EmailChangeRequest.objects.filter(pk=expired_email_req.pk).exists()

    assert AuditLog.objects.filter(pk=audit_log.pk).exists()

    # AuditLog immutability DB trigger also forbids direct DELETE.
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            AuditLog.objects.filter(pk=audit_log.pk).delete()

    with pytest.raises(ValueError, match="batch_size"):
        cleanup_core_data(apply=False, batch_size=0)
