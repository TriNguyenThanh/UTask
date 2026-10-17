from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.response import Response

from apps.messaging.models import IdempotencyRecord
from common import serialization
from common.errors import ClassroomError
from common.responses import build_envelope


def canonical_json(value):
    return serialization.canonical_json(value)


def payload_hash(value):
    return serialization.payload_hash(value)


def require_key(request):
    key = request.headers.get("Idempotency-Key", "")
    if not key:
        raise ClassroomError(
            "IDEMPOTENCY_KEY_REQUIRED", "Yêu cầu thiếu khóa chống trùng lặp (Idempotency-Key)."
        )
    if len(key) > 100 or len(request.path) > 300:
        raise ClassroomError(
            "VALIDATION_ERROR",
            "Khóa chống trùng lặp hoặc đường dẫn yêu cầu vượt quá độ dài cho phép.",
        )
    try:
        return UUID(key)
    except ValueError as exc:
        raise ClassroomError("VALIDATION_ERROR", "Khóa chống trùng lặp phải là UUID.") from exc


def receipt_scope(request, key):
    return {
        "actor_user_id": request.user.id,
        "http_method": request.method,
        "endpoint_path": request.path,
        "idempotency_key": key,
    }


def lookup_receipt(scope, body):
    receipt = IdempotencyRecord.objects.filter(**scope).first()
    if receipt is not None and receipt.payload_hash != payload_hash(body):
        raise ClassroomError(
            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            "Khóa chống trùng lặp đã được sử dụng với nội dung yêu cầu khác.",
            422,
        )
    return receipt


def replay_response(receipt):
    return Response(receipt.response_body, status=receipt.response_status)


def claim_receipt(scope, body, *, status=200):
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt claim requires the command transaction")
    try:
        with transaction.atomic():
            receipt = IdempotencyRecord.objects.create(
                **scope,
                payload_hash=payload_hash(body),
                status="PREPARED",
                expires_at=timezone.now() + timedelta(hours=24),
            )
        return receipt, True
    except IntegrityError as exc:
        if (
            getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
            != "uq_idempotency_scope"
        ):
            raise
        # Query only after the savepoint has rolled back the failed unique INSERT.
        receipt = lookup_receipt(scope, body)
        if receipt is None or not receipt.response_body:
            raise ClassroomError(
                "CONCURRENT_MUTATION_IN_PROGRESS", "Thao tác đang được xử lý.", 409
            ) from exc
        return receipt, False


def save_receipt(scope, body, data, *, status=200, message=None):
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt must commit with mutation")
    envelope = build_envelope(data, **({"message": message} if message is not None else {}))
    receipt = lookup_receipt(scope, body)
    if receipt is not None and receipt.response_body:
        return replay_response(receipt)
    if receipt is None:
        receipt, fresh = claim_receipt(scope, body, status=status)
        if not fresh:
            return replay_response(receipt)
    receipt.status = "COMPLETED"
    receipt.response_status = status
    receipt.response_body = envelope
    receipt.save(update_fields=["status", "response_status", "response_body"])
    return replay_response(receipt)


def begin_receipt(request, body, section=None):
    scope = receipt_scope(request, require_key(request))
    if section is None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [int(payload_hash({k: str(v) for k, v in scope.items()})[:16], 16) % (2**63 - 1)],
            )
    receipt = lookup_receipt(scope, body)
    if receipt is None:
        receipt, _ = claim_receipt(scope, body)
    receipt = IdempotencyRecord.objects.select_for_update().get(pk=receipt.pk)
    if section is not None and receipt.class_section_id is None:
        receipt.class_section = section
        receipt.save(update_fields=["class_section"])
    return receipt


def finish_receipt(receipt, data, *, status=200, message="Đã thực hiện yêu cầu."):
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt must commit with mutation")
    receipt.status = "COMPLETED"
    receipt.response_status = status
    receipt.response_body = build_envelope(data, message)
    receipt.save(update_fields=["status", "response_status", "response_body", "class_section"])
    return replay_response(receipt)
