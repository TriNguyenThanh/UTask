"""Unified idempotency receipt helpers across Identity, Classroom, and Work commands."""

from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.response import Response

from apps.messaging.models import IdempotencyRecord, IdempotencyStatus
from common import serialization
from common.errors import CoreAPIError
from common.locks import LockNamespace, advisory_xact_lock
from common.responses import build_envelope


def canonical_json(value):
    return serialization.canonical_json(value)


def payload_hash(value):
    return serialization.payload_hash(value)


def require_key(request, *, require_uuid: bool = False) -> str:
    key = request.headers.get("Idempotency-Key", "")
    if not key:
        raise CoreAPIError(
            "IDEMPOTENCY_KEY_REQUIRED", "Yêu cầu thiếu khóa chống trùng lặp (Idempotency-Key)."
        )
    if len(key) > 100 or len(request.path) > 300:
        raise CoreAPIError(
            "VALIDATION_ERROR",
            "Khóa chống trùng lặp hoặc đường dẫn yêu cầu vượt quá độ dài cho phép.",
        )
    if require_uuid:
        try:
            return str(UUID(key))
        except ValueError as exc:
            raise CoreAPIError("VALIDATION_ERROR", "Khóa chống trùng lặp phải là UUID.") from exc
    return key


def receipt_scope(request, key: str | UUID, *, domain: str = "work") -> dict[str, str]:
    return {
        "actor_user_id": str(request.user.id),
        "http_method": request.method,
        "endpoint_path": request.path,
        "idempotency_key": str(key),
    }


def lookup_receipt(scope: dict[str, str], body) -> IdempotencyRecord | None:
    receipt = IdempotencyRecord.objects.filter(**scope).first()
    if receipt is not None and receipt.payload_hash != payload_hash(body):
        raise CoreAPIError(
            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            "Khóa chống trùng lặp đã được sử dụng với nội dung yêu cầu khác.",
            status_code=422,
        )
    return receipt


def replay_response(receipt: IdempotencyRecord) -> Response:
    return Response(receipt.response_body, status=receipt.response_status)


def claim_receipt(
    scope: dict[str, str],
    body,
    *,
    domain: str = "work",
    ttl_hours: int = 24,
) -> tuple[IdempotencyRecord, bool]:
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt claim requires the command transaction")
    try:
        with transaction.atomic():
            receipt = IdempotencyRecord.objects.create(
                **scope,
                domain=domain,
                payload_hash=payload_hash(body),
                status=IdempotencyStatus.PREPARED,
                expires_at=timezone.now() + timedelta(hours=ttl_hours),
            )
        return receipt, True
    except IntegrityError as exc:
        if (
            getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
            != "uq_core_idempotency_scope"
        ):
            raise
        receipt = lookup_receipt(scope, body)
        if (
            receipt is None
            or receipt.status != IdempotencyStatus.COMPLETED
            or not receipt.response_body
        ):
            raise CoreAPIError(
                "CONCURRENT_MUTATION_IN_PROGRESS",
                "Thao tác đang được xử lý.",
                status_code=409,
            ) from exc
        return receipt, False


def save_receipt(
    scope: dict[str, str],
    body,
    data,
    *,
    status: int = 200,
    message: str | None = None,
    domain: str = "work",
) -> Response:
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt must commit with mutation")
    envelope = build_envelope(data, **({"message": message} if message is not None else {}))
    receipt = lookup_receipt(scope, body)
    if (
        receipt is not None
        and receipt.status == IdempotencyStatus.COMPLETED
        and receipt.response_body
    ):
        return replay_response(receipt)
    if receipt is None:
        receipt, fresh = claim_receipt(scope, body, domain=domain)
        if not fresh:
            return replay_response(receipt)
    receipt.status = IdempotencyStatus.COMPLETED
    receipt.response_status = status
    receipt.response_body = envelope
    receipt.save(update_fields=["status", "response_status", "response_body"])
    return replay_response(receipt)


def begin_receipt(
    request, body, *, section=None, domain: str = "classroom", require_uuid: bool = True
):
    scope = receipt_scope(request, require_key(request, require_uuid=require_uuid), domain=domain)
    if section is None:
        advisory_xact_lock(LockNamespace.MESSAGING, canonical_json(scope))
    receipt = lookup_receipt(scope, body)
    if receipt is None:
        receipt, _ = claim_receipt(scope, body, domain=domain)
    receipt = IdempotencyRecord.objects.select_for_update().get(pk=receipt.pk)
    if section is not None and receipt.scope_id is None:
        receipt.scope_id = section.pk
        receipt.save(update_fields=["scope_id"])
    return receipt


def finish_receipt(
    receipt: IdempotencyRecord,
    data,
    *,
    status: int = 200,
    message: str = "Đã thực hiện yêu cầu.",
) -> Response:
    if not connection.in_atomic_block:
        raise RuntimeError("Receipt must commit with mutation")
    receipt.status = IdempotencyStatus.COMPLETED
    receipt.response_status = status
    receipt.response_body = build_envelope(data, message)
    receipt.save(update_fields=["status", "response_status", "response_body", "scope_id"])
    return replay_response(receipt)
