from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.response import Response

from apps.messaging.models import IdempotencyRecord
from common import serialization
from common.errors import WorkError
from common.responses import build_envelope


def canonical_json(value):
    return serialization.canonical_json(value)


def payload_hash(value):
    return serialization.payload_hash(value)


def require_key(request):
    key = request.headers.get("Idempotency-Key", "")
    if not key:
        raise WorkError(
            "IDEMPOTENCY_KEY_REQUIRED", "Yêu cầu thiếu khóa chống trùng lặp (Idempotency-Key)."
        )
    if len(key) > 100 or len(request.path) > 300:
        raise WorkError(
            "VALIDATION_ERROR",
            "Khóa chống trùng lặp hoặc đường dẫn yêu cầu vượt quá độ dài cho phép.",
        )
    return key


def receipt_scope(request, key):
    return {
        "user_id": request.user.id,
        "http_method": request.method,
        "endpoint_path": request.path,
        "idempotency_key": key,
    }


def lookup_receipt(scope, body):
    receipt = IdempotencyRecord.objects.filter(**scope).first()
    if receipt is not None and receipt.payload_hash != payload_hash(body):
        raise WorkError(
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
                response_status=status,
                response_body={},
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
            raise WorkError(
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
    receipt.response_status = status
    receipt.response_body = envelope
    receipt.save(update_fields=["response_status", "response_body"])
    return replay_response(receipt)
