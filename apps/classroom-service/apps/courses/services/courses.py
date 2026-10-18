from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import Course
from apps.courses.permissions import require_role
from apps.courses.serializers.courses import CourseSerializer
from apps.messaging.services.receipts import begin_receipt, finish_receipt, replay_response


def save_course(request, payload, course_id=None, *, archive=False):
    require_role(request, "SYSTEM_ADMIN")
    with transaction.atomic():
        receipt = begin_receipt(request, payload)
        if receipt.status == "COMPLETED":
            return replay_response(receipt)
        course = (
            get_object_or_404(Course.objects.select_for_update(), pk=course_id)
            if course_id
            else Course()
        )
        if archive:
            course.archived_at = timezone.now()
        else:
            for key, value in payload.items():
                setattr(course, key, value)
        course.save()
        return finish_receipt(
            receipt,
            CourseSerializer(course).data,
            status=200 if course_id else 201,
            message="Đã lưu thông tin môn học.",
        )
