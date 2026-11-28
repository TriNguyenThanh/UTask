"""Classroom JSON provisioning: scoped receipt, ordered locks, per-row savepoints."""

import hashlib
import json
from uuid import UUID

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.accounts.models import AccountStatus, User
from apps.accounts.serializers.provisioning import StudentRowSerializer
from apps.accounts.services.account_access import (
    account_audit,
    lock_accounts,
    lock_accounts_for_actor,
    record_account_audit,
)
from apps.messaging.models import IdempotencyRecord, IdempotencyStatus
from apps.messaging.services.outbox import emit_identity_user
from common.errors import CoreAPIError
from common.locks import LockNamespace, advisory_xact_lock
from common.responses import build_envelope


class RetryAccountLocks(Exception):
    """An identity appeared after discovery: restart the whole ordered transaction."""


def canonical_students(rows):
    result = []
    for row in rows:
        normalized = dict(row)
        if isinstance(row.get("email"), str):
            normalized["email"] = User.objects.normalize_email(row["email"])
        if isinstance(row.get("student_id"), str) or row.get("student_id") is None:
            normalized["student_id"] = User.objects.normalize_student_id(row.get("student_id"))
        result.append(normalized)
    return result


def identity_query(rows):
    emails = [
        row.get("email") for row in rows if isinstance(row.get("email"), str) and row["email"]
    ]
    ids = [
        row.get("student_id")
        for row in rows
        if isinstance(row.get("student_id"), str) and row["student_id"]
    ]
    return Q(email__in=emails) | Q(student_id__in=ids)


def provision_row(
    actor_id,
    data,
    locked_ids,
    *,
    ip_address: str = "",
    user_agent: str = "",
    native_request=None,
):
    matches = list(User.objects.filter(identity_query([data])).order_by("pk"))
    if any(user.pk not in locked_ids for user in matches):
        raise RetryAccountLocks()
    if len(matches) > 1:
        return None, "IDENTITY_CONFLICT"
    if matches:
        user = matches[0]
        if data["email"] and user.email != data["email"]:
            return None, "IDENTITY_CONFLICT"
        if user.deleted_at or user.account_status not in {
            AccountStatus.ACTIVE,
            AccountStatus.PENDING_ACTIVATION,
        }:
            return None, "ACCOUNT_UNAVAILABLE"
        roles = set(user.global_role_assignments.values_list("role__code", flat=True))
        if roles != {"STUDENT"}:
            return None, "FLAGGED_ROLE_CONFLICT"
        if data["student_id"] and user.student_id not in {None, data["student_id"]}:
            return None, "IDENTITY_CONFLICT"
        if user.student_id is None and data["student_id"]:
            user.student_id = data["student_id"]
            user.save(update_fields=("student_id", "updated_at"))
            record_account_audit(
                actor_id,
                user,
                "STUDENT_ID_ASSIGNED",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            emit_identity_user(user, "identity.user.updated")
        return user, "EXISTING"
    if not data["email"]:
        return None, "STUDENT_ID_NOT_FOUND"
    if settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION:
        user = User.objects.create_user(
            email=data["email"],
            student_id=data["student_id"],
            password=None,
            first_name=data["first_name"],
            last_name=data["last_name"],
            account_status=AccountStatus.PENDING_ACTIVATION,
        )
        user.profile.refresh_from_db(fields=("display_name",))
        address = EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=False
        )
        user._identity_activation_event = "identity.student.imported"
        address.send_confirmation(native_request)
    else:
        # Local/dev bypass when SMTP is not yet enabled.
        user = User.objects.create_user(
            email=data["email"],
            student_id=data["student_id"],
            password=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            account_status=AccountStatus.ACTIVE,
        )
        user.profile.refresh_from_db(fields=("display_name",))
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    locked_ids.add(user.pk)
    record_account_audit(
        actor_id,
        user,
        "STUDENT_IMPORTED",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    emit_identity_user(user)
    return user, "CREATED"


def _resolve_provisioning_caller(actor_or_request, endpoint_path: str | None):
    if hasattr(actor_or_request, "user") and hasattr(actor_or_request, "META"):
        request = actor_or_request
        return (
            request,
            request.user.pk,
            endpoint_path or request.path,
            request.META.get("REMOTE_ADDR", ""),
            request.META.get("HTTP_USER_AGENT", ""),
            getattr(request, "_request", request),
        )
    actor_id = (
        actor_or_request.pk if hasattr(actor_or_request, "pk") else UUID(str(actor_or_request))
    )
    return (
        None,
        actor_id,
        endpoint_path or "/api/v1/internal/users/provision-students",
        "",
        "core-service/in-process",
        None,
    )


def provision_students(actor_or_request, rows, key, *, endpoint_path: str | None = None):
    if not key:
        raise CoreAPIError("IDEMPOTENCY_KEY_REQUIRED", "Thiếu mã chống xử lý lặp cho yêu cầu.")
    try:
        key = str(UUID(str(key)))
    except ValueError as exc:
        raise CoreAPIError("VALIDATION_ERROR", "Mã chống xử lý lặp không đúng định dạng.") from exc

    request, actor_id, resolved_path, ip_address, user_agent, native_request = (
        _resolve_provisioning_caller(actor_or_request, endpoint_path)
    )
    rows = canonical_students(rows)
    payload = json.dumps(
        {"students": rows}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    scope = {
        "actor_user_id": str(actor_id),
        "http_method": "POST",
        "endpoint_path": resolved_path,
        "idempotency_key": key,
    }
    lock_key = json.dumps(scope, sort_keys=True)
    for _attempt in range(3):
        try:
            with transaction.atomic():
                # Transaction-scoped advisory lock serializes claim even before a receipt exists.
                advisory_xact_lock(LockNamespace.IDENTITY, lock_key)
                targets = list(
                    User.objects.filter(identity_query(rows)).values_list("pk", flat=True)
                )
                if request is not None and getattr(request, "auth", None) is not None:
                    users = lock_accounts(request, targets, roles={"TEACHER", "SYSTEM_ADMIN"})
                else:
                    users = lock_accounts_for_actor(
                        actor_id, targets, roles={"TEACHER", "SYSTEM_ADMIN"}
                    )
                locked_ids = set(users)
                receipt = IdempotencyRecord.objects.filter(**scope).first()
                if receipt:
                    if receipt.payload_hash != digest:
                        raise CoreAPIError(
                            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
                            "Mã chống xử lý lặp đã được dùng cho nội dung khác. "
                            "Vui lòng tạo yêu cầu mới.",
                            status_code=422,
                        )
                    if (
                        receipt.status != IdempotencyStatus.COMPLETED
                        or receipt.response_body is None
                    ):
                        raise CoreAPIError(
                            "CONCURRENT_MUTATION_IN_PROGRESS",
                            "Thao tác đang được xử lý. Vui lòng kiểm tra lại kết quả.",
                            status_code=409,
                        )
                    return receipt.response_status, receipt.response_body
                results = []
                summary = {
                    "total_records": len(rows),
                    "created_accounts": 0,
                    "existing_accounts": 0,
                    "flagged_records": 0,
                    "failed_records": 0,
                }
                for row in rows:
                    serializer = StudentRowSerializer(data=row)
                    user = None
                    if not serializer.is_valid():
                        result = reason = "VALIDATION_ERROR"
                    else:
                        try:
                            with transaction.atomic():
                                user, result = provision_row(
                                    actor_id,
                                    serializer.validated_data,
                                    locked_ids,
                                    ip_address=ip_address,
                                    user_agent=user_agent,
                                    native_request=native_request,
                                )
                        except IntegrityError:
                            # Discover/lock the winner on the next whole transaction attempt.
                            raise RetryAccountLocks() from None
                        reason = None if user else result
                    counter = {
                        "CREATED": "created_accounts",
                        "EXISTING": "existing_accounts",
                        "FLAGGED_ROLE_CONFLICT": "flagged_records",
                    }.get(result, "failed_records")
                    summary[counter] += 1
                    results.append(
                        {
                            "row_number": row.get("row_number"),
                            "user_id": str(user.pk) if user else None,
                            "email": user.email if user else row.get("email"),
                            "student_id": user.student_id if user else row.get("student_id"),
                            "account_status": user.account_status if user else None,
                            "account_result": result
                            if user
                            else ("FLAGGED" if counter == "flagged_records" else "FAILED"),
                            "reason": reason,
                        }
                    )
                status_code = 201 if summary["created_accounts"] else 200
                body = build_envelope(
                    {"summary": summary, "results": results}, "Đã xử lý danh sách tài khoản."
                )
                IdempotencyRecord.objects.create(
                    domain="identity",
                    **scope,
                    payload_hash=digest,
                    status=IdempotencyStatus.COMPLETED,
                    response_status=status_code,
                    response_body=body,
                )
                return status_code, body
        except RetryAccountLocks:
            continue
    raise CoreAPIError(
        "IDENTITY_UNAVAILABLE",
        "Không thể hoàn tất việc cấp tài khoản. Vui lòng thử lại.",
        status_code=503,
    )


def resend_import_activation(request, target_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"TEACHER", "SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None or user.deleted_at:
            raise CoreAPIError("RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404)
        if user.account_status == AccountStatus.ACTIVE:
            raise CoreAPIError("ACCOUNT_ALREADY_ACTIVE", "Tài khoản đã kích hoạt.")
        if user.account_status != AccountStatus.PENDING_ACTIVATION:
            raise CoreAPIError("ACCOUNT_UNAVAILABLE", "Tài khoản không đủ điều kiện.")
        address = EmailAddress.objects.get(user=user, primary=True)
        address.send_confirmation(getattr(request, "_request", request))
        account_audit(request, user, "ACTIVATION_RESENT")
