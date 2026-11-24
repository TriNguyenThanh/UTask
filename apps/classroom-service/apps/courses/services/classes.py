from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from apps.courses.models import ClassSection, ClassTeacher, Course, Enrollment
from apps.courses.permissions import (
    actor_roles,
    bearer,
    require_manage,
    require_open,
    require_read,
    require_role,
)
from apps.courses.serializers.classes import ClassSerializer, TeacherSerializer
from apps.groups.models import StudyGroup
from apps.messaging.services.audit import record_activity
from apps.messaging.services.receipts import (
    begin_receipt,
    finish_receipt,
    lookup_receipt,
    receipt_scope,
    replay_response,
    require_key,
)
from common.access_codes import code_hash, generate_code
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient


def lock_class(class_id):
    return get_object_or_404(ClassSection.objects.select_for_update(), pk=class_id)


def check_version(section, expected):
    if section.version != expected:
        raise ClassroomError(
            "VERSION_CONFLICT", "Lớp học đã thay đổi. Vui lòng tải lại dữ liệu.", 409
        )


def verified_teacher(request, user_id):
    users = IdentityClient().users(bearer(request), [user_id])
    if (
        not users
        or str(users[0]["id"]) != str(user_id)
        or "TEACHER" not in users[0].get("roles", [])
        or users[0].get("account_status") != "ACTIVE"
    ):
        raise ClassroomError(
            "INVALID_TEACHER", "Hãy chọn giảng viên có tài khoản đang hoạt động.", 422
        )


def create_class(request, payload):
    require_role(request, "TEACHER", "SYSTEM_ADMIN")
    saved = lookup_receipt(receipt_scope(request, require_key(request)), payload)
    if saved is not None and saved.status == "COMPLETED":
        with transaction.atomic():
            section = lock_class(saved.class_section_id)
            require_manage(request, section)
            return replay_response(saved)
    teacher_id = payload.get("primary_teacher_id", request.user.id)
    if teacher_id != request.user.id and "SYSTEM_ADMIN" not in actor_roles(request):
        raise ClassroomError(
            "PERMISSION_DENIED",
            "Chỉ quản trị viên được tạo lớp cho giảng viên khác phụ trách.",
            403,
        )
    if "TEACHER" not in actor_roles(request) or teacher_id != request.user.id:
        verified_teacher(request, teacher_id)
    with transaction.atomic():
        receipt = begin_receipt(request, payload)
        if receipt.status == "COMPLETED":
            section = lock_class(receipt.class_section_id)
            require_manage(request, section)
            return replay_response(receipt)
        course = get_object_or_404(
            Course.objects.select_for_update(), pk=payload["course_id"], archived_at__isnull=True
        )
        section = ClassSection.objects.create(
            course=course,
            **{k: v for k, v in payload.items() if k not in {"course_id", "primary_teacher_id"}},
        )
        ClassTeacher.objects.create(class_section=section, user_id=teacher_id, role="PRIMARY")
        record_activity(
            section, request.user.id, "class.created", new=ClassSerializer(section).data
        )
        receipt.class_section = section
        return finish_receipt(
            receipt,
            ClassSerializer(section).data,
            status=201,
            message="Đã tạo lớp học và phân công giảng viên chính.",
        )


def change_class(request, class_id, payload, *, action="update"):
    actor_roles(request)
    saved = lookup_receipt(receipt_scope(request, require_key(request)), payload)
    if (
        action == "teacher"
        and payload["status"] == "ACTIVE"
        and not (saved is not None and saved.status == "COMPLETED")
    ):
        # Reject callers outside the class before looking up another account.
        # The locked checks below remain authoritative if assignment changes during HTTP.
        section = get_object_or_404(ClassSection, pk=class_id)
        require_read(request, section)
        require_manage(request, section)
        require_open(section)
        verified_teacher(request, payload["user_id"])
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        if action != "state":
            require_open(section)
        check_version(section, payload["version"])
        if action == "update":
            values = {k: v for k, v in payload.items() if k != "version"}
            if values.get("starts_on", section.starts_on) > values.get(
                "ends_on", section.ends_on
            ) or values.get("group_min_size", section.group_min_size) > values.get(
                "group_max_size", section.group_max_size
            ):
                raise ClassroomError(
                    "VALIDATION_ERROR", "Ngày học hoặc giới hạn thành viên không hợp lệ."
                )
            largest = (
                StudyGroup.objects.filter(class_section=section, status="ACTIVE")
                .annotate(size=Count("members", filter=Q(members__status="ACTIVE")))
                .order_by("-size")
                .first()
            )
            if largest and largest.size > values.get("group_max_size", section.group_max_size):
                raise ClassroomError(
                    "GROUP_CAPACITY_CONFLICT",
                    "Giới hạn mới nhỏ hơn số thành viên hiện có trong nhóm.",
                    409,
                )
            for field, value in values.items():
                setattr(section, field, value)
        elif action == "state":
            if section.status == "ARCHIVED" and payload["status"] != "ARCHIVED":
                raise ClassroomError("CLASS_ARCHIVED", "Lớp đã lưu trữ không thể mở lại.", 409)
            section.status = payload["status"]
        elif action == "lock-grouping":
            if section.grouping_phase == "LOCKED":
                return finish_receipt(
                    receipt,
                    ClassSerializer(section, context={"actor_id": request.user.id}).data,
                    message="Lớp học đã ở trạng thái chốt lập nhóm.",
                )
            if not payload.get("force", False):
                unassigned_count = (
                    Enrollment.objects.filter(class_section=section, status="ACTIVE")
                    .exclude(memberships__status="ACTIVE", memberships__group__status="ACTIVE")
                    .count()
                )
                undersized = list(
                    StudyGroup.objects.filter(class_section=section, status="ACTIVE")
                    .annotate(active_count=Count("members", filter=Q(members__status="ACTIVE")))
                    .filter(active_count__lt=section.group_min_size)
                    .order_by("created_at", "id")
                    .values("id", "name", "active_count")
                )
                if unassigned_count > 0 or undersized:
                    details = []
                    if unassigned_count > 0:
                        details.append(
                            {
                                "field": "unassigned_students",
                                "issue": (
                                    f"Còn {unassigned_count} sinh viên đang ghi danh nhưng chưa "
                                    "thuộc nhóm học tập nào."
                                ),
                            }
                        )
                    for item in undersized:
                        details.append(
                            {
                                "field": f"groups.{item['id']}",
                                "issue": (
                                    f'Nhóm "{item["name"]}" hiện có '
                                    f"{item['active_count']}/{section.group_min_size} "
                                    "thành viên tối thiểu."
                                ),
                            }
                        )
                    raise ClassroomError(
                        "GROUPING_PRECONDITIONS_UNMET",
                        (
                            "Chưa đáp ứng điều kiện chốt lập nhóm. Vui lòng xử lý các mục còn "
                            "thiếu hoặc xác nhận vẫn chốt lập nhóm."
                        ),
                        409,
                        details=details,
                    )
            section.grouping_phase = "LOCKED"
            section.grouping_locked_at = section.grouping_locked_at or timezone.now()
        elif action == "unlock-grouping":
            if section.grouping_phase == "FORMING":
                return finish_receipt(
                    receipt,
                    ClassSerializer(section, context={"actor_id": request.user.id}).data,
                    message="Lớp học hiện đang ở trạng thái mở chia nhóm.",
                )
            section.grouping_phase = "FORMING"
            section.grouping_locked_at = None
        elif action == "teacher":
            teacher = ClassTeacher.objects.filter(
                class_section=section, user_id=payload["user_id"]
            ).first()
            if (
                teacher
                and teacher.status == "ACTIVE"
                and payload["status"] == "LEFT"
                and not section.teachers.filter(status="ACTIVE").exclude(pk=teacher.pk).exists()
            ):
                raise ClassroomError(
                    "LAST_TEACHER_REQUIRED", "Lớp phải còn giảng viên phụ trách.", 409
                )
            teacher, _ = ClassTeacher.objects.update_or_create(
                class_section=section,
                user_id=payload["user_id"],
                defaults={
                    "role": payload["role"],
                    "status": payload["status"],
                    "left_at": timezone.now() if payload["status"] == "LEFT" else None,
                },
            )
            record_activity(
                teacher,
                request.user.id,
                "class.teacher.changed",
                new=TeacherSerializer(teacher).data,
            )
        section.version += 1
        section.save()
        serialized = ClassSerializer(section, context={"actor_id": request.user.id}).data
        activity_verb = (
            "class.grouping_unlocked" if action == "unlock-grouping" else "class." + action
        )
        activity_new = (
            {"reason": payload["reason"], "version": section.version}
            if action == "unlock-grouping"
            else serialized
        )
        record_activity(section, request.user.id, activity_verb, new=activity_new)
        return finish_receipt(
            receipt,
            serialized,
            message={
                "update": "Đã cập nhật thông tin lớp học.",
                "state": "Đã cập nhật trạng thái lớp học.",
                "lock-grouping": "Đã chốt giai đoạn lập nhóm của lớp học.",
                "unlock-grouping": "Đã mở khóa giai đoạn lập nhóm của lớp học.",
                "teacher": "Đã cập nhật phân công giảng viên phụ trách.",
            }[action],
        )


def issue_class_code(request, class_id, payload):
    actor_roles(request)
    with transaction.atomic():
        section = lock_class(class_id)
        require_read(request, section)
        require_manage(request, section)
        receipt = begin_receipt(request, payload, section)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        require_open(section)
        check_version(section, payload["version"])
        enabled = payload["enabled"]
        expires = payload.get("expires_at", timezone.now() + timedelta(days=7)) if enabled else None
        if expires and expires <= timezone.now():
            raise ClassroomError("VALIDATION_ERROR", "Thời hạn mã phải ở tương lai.")
        code = None
        for _ in range(5):
            code = generate_code() if enabled else None
            try:
                with transaction.atomic():
                    section.join_code_hash = code_hash(code) if enabled else None
                    section.join_code_expires_at = expires
                    section.version += 1
                    section.save()
                break
            except IntegrityError as exc:
                section.version -= 1
                if (
                    getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
                    != "uq_class_sections_join_code"
                ):
                    raise
        else:
            raise ClassroomError("ACCESS_CODE_UNAVAILABLE", "Chưa thể cấp mã tham gia.", 503)
        record_activity(section, request.user.id, "class.code.changed", new={"enabled": enabled})
        response = finish_receipt(
            receipt,
            {
                "id": str(section.pk),
                "version": section.version,
                "expires_at": expires,
                "enabled": enabled,
            },
            message="Đã cấp mã tham gia lớp học." if enabled else "Đã tắt mã tham gia lớp học.",
        )
        if code:
            response = Response({**response.data, "data": {**response.data["data"], "code": code}})
        return response
