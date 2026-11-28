from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import Course
from apps.courses.permissions import actor_roles, require_role
from apps.courses.serializers.courses import CourseSerializer
from apps.messaging.services.receipts import begin_receipt, finish_receipt, replay_response
from common.errors import CoreAPIError


def save_course(request, payload, course_id=None, *, archive=False, unarchive=False):
    if archive and unarchive:
        raise ValueError("Cannot archive and unarchive a course in the same operation.")
    require_role(request, "TEACHER", "SYSTEM_ADMIN")
    with transaction.atomic():
        course = (
            get_object_or_404(Course.objects.select_for_update(), pk=course_id)
            if course_id
            else Course(created_by_id=request.user.id)
        )
        if (
            course_id
            and "SYSTEM_ADMIN" not in actor_roles(request)
            and course.created_by_id != request.user.id
        ):
            raise CoreAPIError(
                "PERMISSION_DENIED", "Bạn chỉ có quyền quản lý môn học do mình tạo.", 403
            )
        receipt = begin_receipt(request, payload, domain="classroom", require_uuid=True)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        if archive:
            course.archived_at = timezone.now()
        elif unarchive:
            course.archived_at = None
        else:
            for key, value in payload.items():
                setattr(course, key, value)
        course.save()
        return finish_receipt(
            receipt,
            CourseSerializer(course).data,
            status=200 if course_id else 201,
            message="Đã mở lại môn học." if unarchive else "Đã lưu thông tin môn học.",
        )
