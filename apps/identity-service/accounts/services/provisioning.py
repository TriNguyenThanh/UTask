"""Classroom JSON provisioning: scoped receipt, ordered locks, per-row savepoints."""

import hashlib
import json
from uuid import UUID

from allauth.account.models import EmailAddress
from django.db import IntegrityError, connection, transaction
from django.db.models import Q

from accounts.models import AccountStatus, IdempotencyRecord, User
from accounts.serializers.provisioning import StudentRowSerializer
from accounts.services.account_access import account_audit, lock_accounts
from common.errors import IdentityAPIError
from common.responses import build_envelope
from messaging.outbox import emit_user


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


def provision_row(request, data, locked_ids):
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
            account_audit(request, user, "STUDENT_ID_ASSIGNED")
            emit_user(user, "identity.user.updated")
        return user, "EXISTING"
    if not data["email"]:
        return None, "STUDENT_ID_NOT_FOUND"
    user = User.objects.create_user(
        email=data["email"],
        student_id=data["student_id"],
        password=None,
        first_name=data["first_name"],
        last_name=data["last_name"],
        account_status=AccountStatus.PENDING_ACTIVATION,
    )
    locked_ids.add(user.pk)
    account_audit(request, user, "STUDENT_IMPORTED")
    emit_user(user)
    user._identity_activation_event = "identity.student.imported"
    address = EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)
    address.send_confirmation(request)
    return user, "CREATED"


def provision_students(request, rows, key):
    if not key:
        raise IdentityAPIError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key là bắt buộc.")
    try:
        key = str(UUID(key))
    except ValueError as exc:
        raise IdentityAPIError("VALIDATION_ERROR", "Idempotency-Key phải là UUID.") from exc
    rows = canonical_students(rows)
    payload = json.dumps(
        {"students": rows}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    scope = {"user_id": str(request.user.pk), "endpoint_path": request.path, "idempotency_key": key}
    lock_hash = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).digest()[:8]
    for _attempt in range(3):
        try:
            with transaction.atomic():
                # Transaction-scoped tuple lock serializes claim even before a receipt exists.
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(%s)",
                        [int.from_bytes(lock_hash, "big", signed=True)],
                    )
                targets = list(
                    User.objects.filter(identity_query(rows)).values_list("pk", flat=True)
                )
                users = lock_accounts(request, targets, roles={"TEACHER", "SYSTEM_ADMIN"})
                locked_ids = set(users)
                receipt = IdempotencyRecord.objects.filter(**scope).first()
                if receipt:
                    if receipt.payload_hash != digest:
                        raise IdentityAPIError(
                            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
                            "Idempotency-Key đã dùng với nội dung khác.",
                            status_code=422,
                        )
                    return receipt.response_status, receipt.response_body
                results = []
                summary = dict(
                    total_records=len(rows),
                    created_accounts=0,
                    existing_accounts=0,
                    flagged_records=0,
                    failed_records=0,
                )
                for row in rows:
                    serializer = StudentRowSerializer(data=row)
                    user = None
                    if not serializer.is_valid():
                        result = reason = "VALIDATION_ERROR"
                    else:
                        try:
                            with transaction.atomic():
                                user, result = provision_row(
                                    request, serializer.validated_data, locked_ids
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
                status = 201 if summary["created_accounts"] else 200
                body = build_envelope(
                    {"summary": summary, "results": results}, "Đã xử lý danh sách tài khoản."
                )
                IdempotencyRecord.objects.create(
                    **scope, payload_hash=digest, response_status=status, response_body=body
                )
                return status, body
        except RetryAccountLocks:
            continue
    raise IdentityAPIError(
        "IDENTITY_UNAVAILABLE", "Không thể khóa danh tính an toàn; hãy retry.", status_code=503
    )


def resend_import_activation(request, target_id):
    with transaction.atomic():
        users = lock_accounts(request, [target_id], roles={"TEACHER", "SYSTEM_ADMIN"})
        user = users.get(target_id)
        if user is None or user.deleted_at:
            raise IdentityAPIError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404
            )
        if user.account_status == AccountStatus.ACTIVE:
            raise IdentityAPIError("ACCOUNT_ALREADY_ACTIVE", "Tài khoản đã kích hoạt.")
        if user.account_status != AccountStatus.PENDING_ACTIVATION:
            raise IdentityAPIError("ACCOUNT_UNAVAILABLE", "Tài khoản không đủ điều kiện.")
        address = EmailAddress.objects.get(user=user, primary=True)
        address.send_confirmation(request)
        account_audit(request, user, "ACTIVATION_RESENT")
