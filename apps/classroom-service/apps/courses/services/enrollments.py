from uuid import UUID, uuid4

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import ClassSection, Enrollment
from apps.courses.permissions import (
    actor_roles,
    bearer,
    require_manage,
    require_open,
    require_read,
    require_role,
)
from apps.courses.serializers.enrollments import EnrollmentSerializer
from apps.courses.services.classes import lock_class
from apps.messaging.services.audit import record_activity
from apps.messaging.services.receipts import (
    begin_receipt,
    finish_receipt,
    lookup_receipt,
    receipt_scope,
    replay_response,
    require_key,
)
from common.access_codes import code_hash
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient


def join_class(request, payload):
    require_role(request, "STUDENT")
    digest = code_hash(payload["code"])
    with transaction.atomic():
        saved = lookup_receipt(receipt_scope(request, require_key(request)), payload)
        section = (
            lock_class(saved.class_section_id)
            if saved is not None and saved.status == "COMPLETED"
            else get_object_or_404(ClassSection.objects.select_for_update(), join_code_hash=digest)
        )
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            require_read(request, section)
            return replay_response(receipt)
        require_role(request, "STUDENT")
        require_open(section)
        if not section.join_code_expires_at or section.join_code_expires_at <= timezone.now():
            raise ClassroomError(
                "ACCESS_CODE_EXPIRED", "Mã tham gia lớp đã hết hạn. Hãy xin mã mới.", 409
            )
        enrollment, created = Enrollment.objects.get_or_create(
            class_section=section, user_id=request.user.id
        )
        if enrollment.status != "ACTIVE":
            raise ClassroomError(
                "ENROLLMENT_INACTIVE",
                (
                    "Bạn đã rời hoặc bị loại khỏi lớp học này. "
                    "Vui lòng liên hệ giảng viên phụ trách để được khôi phục ghi danh."
                ),
                409,
            )
        if created:
            record_activity(
                enrollment, request.user.id, "enrollment.joined", new={"user_id": request.user.id}
            )
        return finish_receipt(
            receipt,
            EnrollmentSerializer(enrollment).data,
            status=201 if created else 200,
            message="Bạn đã tham gia lớp học.",
        )


def add_students(request, class_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if receipt.upstream_key is None:
            receipt.upstream_key = uuid4()
            receipt.save(update_fields=["upstream_key"])
        upstream_key = receipt.upstream_key
    # Remote provisioning must never hold the class or receipt transaction open.
    emails, student_ids, unique_rows, unique_indices, duplicates = set(), set(), [], [], set()
    for index, row in enumerate(payload["students"]):
        email = row.get("email")
        email = email.strip().lower() if isinstance(email, str) else None
        student_id = row.get("student_id")
        student_id = student_id.strip().upper() if isinstance(student_id, str) else None
        if (email and email in emails) or (student_id and student_id in student_ids):
            duplicates.add(index)
            continue
        if email:
            emails.add(email)
        if student_id:
            student_ids.add(student_id)
        unique_indices.append(index)
        unique_rows.append(row)
    upstream = IdentityClient().provision(bearer(request), unique_rows, upstream_key)
    by_index = dict(zip(unique_indices, upstream["results"], strict=True))
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        results = []
        seen = set()
        for index, original in enumerate(payload["students"]):
            item = (
                by_index.get(index)
                if index not in duplicates
                else {
                    "row_number": original.get("row_number"),
                    "email": original.get("email"),
                    "student_id": original.get("student_id"),
                    "account_result": "NOT_REQUESTED",
                    "reason": "DUPLICATE_IN_LIST",
                }
            )
            row = {
                key: item.get(key)
                for key in [
                    "row_number",
                    "user_id",
                    "email",
                    "student_id",
                    "account_status",
                    "account_result",
                    "reason",
                ]
            }
            row["enrollment_result"] = "FAILED"
            user_id = None
            if item["account_result"] in {"EXISTING", "CREATED"}:
                try:
                    user_id = UUID(item["user_id"])
                    if item.get("account_status") not in {"ACTIVE", "PENDING_ACTIVATION"}:
                        raise ValueError()
                except (ValueError, TypeError, KeyError) as exc:
                    raise ClassroomError(
                        "IDENTITY_UNAVAILABLE",
                        "Không thể xác minh kết quả tài khoản sinh viên.",
                        503,
                    ) from exc
            if row["row_number"] != payload["students"][index].get("row_number"):
                raise ClassroomError(
                    "IDENTITY_UNAVAILABLE", "Không thể đối chiếu kết quả danh sách tài khoản.", 503
                )
            if user_id in seen:
                row["reason"] = "DUPLICATE_STUDENT"
            elif user_id:
                seen.add(user_id)
                reactivate_inactive = bool(payload.get("reactivate_inactive", False))
                with transaction.atomic():
                    enrollment, created = Enrollment.objects.get_or_create(
                        class_section=section,
                        user_id=user_id,
                        defaults={
                            "source": "TEACHER" if len(payload["students"]) == 1 else "BATCH"
                        },
                    )
                    row["enrollment_id"] = str(enrollment.pk)
                    row["enrollment_result"] = "ENROLLED" if created else "ALREADY_ENROLLED"
                    if enrollment.status != "ACTIVE":
                        if reactivate_inactive:
                            old_status = enrollment.status
                            enrollment.status = "ACTIVE"
                            enrollment.left_at = None
                            enrollment.save(update_fields=["status", "left_at"])
                            row["enrollment_result"] = "REACTIVATED"
                            row["reason"] = None
                            record_activity(
                                enrollment,
                                request.user.id,
                                "enrollment.reactivated",
                                old={"status": old_status},
                                new={"status": "ACTIVE", "user_id": user_id},
                            )
                        else:
                            row["enrollment_result"] = "FAILED"
                            row["reason"] = "ENROLLMENT_INACTIVE"
                    elif created:
                        record_activity(
                            enrollment,
                            request.user.id,
                            "enrollment.added",
                            new={"user_id": user_id},
                        )
            results.append(row)
        summary = {
            "total_records": len(results),
            "enrolled": sum(row["enrollment_result"] == "ENROLLED" for row in results),
            "already_enrolled": sum(
                row["enrollment_result"] == "ALREADY_ENROLLED" for row in results
            ),
            "reactivated": sum(row["enrollment_result"] == "REACTIVATED" for row in results),
            "failed": sum(row["enrollment_result"] == "FAILED" for row in results),
            "created_accounts": sum(row["account_result"] == "CREATED" for row in results),
            "existing_accounts": sum(row["account_result"] == "EXISTING" for row in results),
            "flagged": sum(row["account_result"] == "FLAGGED" for row in results),
            "duplicates": sum(
                row["reason"] in {"DUPLICATE_IN_LIST", "DUPLICATE_STUDENT"} for row in results
            ),
        }
        return finish_receipt(
            receipt,
            {"summary": summary, "results": results},
            message="Đã xử lý danh sách sinh viên và kết quả ghi danh.",
        )


def reactivate_enrollment(request, class_id, enrollment_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        enrollment = get_object_or_404(
            Enrollment.objects.select_for_update(), pk=enrollment_id, class_section=section
        )
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        if enrollment.status == "ACTIVE":
            raise ClassroomError(
                "ENROLLMENT_ALREADY_ACTIVE",
                "Sinh viên hiện đang ghi danh hoạt động trong lớp học này.",
                409,
            )
        old_status = enrollment.status
        enrollment.status = "ACTIVE"
        enrollment.left_at = None
        enrollment.save(update_fields=["status", "left_at"])
        record_activity(
            enrollment,
            request.user.id,
            "enrollment.reactivated",
            old={"status": old_status},
            new={"status": "ACTIVE", "reason": payload["reason"]},
        )
        return finish_receipt(
            receipt,
            EnrollmentSerializer(enrollment).data,
            message="Đã khôi phục sinh viên vào lớp học.",
        )


def exit_class(request, class_id, enrollment_id, payload):
    actor_roles(request)
    from apps.groups.models import GroupMember, StudyGroup
    from apps.groups.services.members import end_membership

    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id, class_section=section)
        own = enrollment.user_id == request.user.id
        if not own:
            require_manage(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        membership = GroupMember.objects.filter(enrollment=enrollment, status="ACTIVE").first()
        if membership:
            require_open(section, forming=own)
            source_group = StudyGroup.objects.select_for_update().get(pk=membership.group_id)
            end_membership(
                section,
                source_group,
                membership,
                request.user.id,
                "LEFT" if own else "REMOVED",
                payload["reason"],
                dissolve_if_sole_member=bool(payload.get("dissolve_if_sole_member", False)),
            )
        enrollment.status = "LEFT" if own else "REMOVED"
        enrollment.left_at = timezone.now()
        enrollment.save(update_fields=["status", "left_at"])
        from apps.groups.services.join_requests import cancel_pending_join_requests

        cancel_pending_join_requests(
            actor_id=request.user.id,
            note="Sinh viên đã kết thúc ghi danh trong lớp học.",
            class_section=section,
            enrollment=enrollment,
        )
        record_activity(
            enrollment,
            request.user.id,
            "enrollment.exited",
            new={"status": enrollment.status, "reason": payload["reason"]},
        )
        return finish_receipt(
            receipt,
            EnrollmentSerializer(enrollment).data,
            message="Đã kết thúc việc ghi danh và cập nhật thành viên nhóm liên quan.",
        )
