from django.db.models import Q

from apps.accounts.interface import get_user_roles
from apps.courses.models import ClassSection, ClassTeacher, Course, Enrollment
from common.errors import CoreAPIError


def actor_roles(request) -> set[str]:
    if not hasattr(request, "classroom_roles"):
        request.classroom_roles = set(get_user_roles(request.user.id))
    return request.classroom_roles


def require_role(request, *roles):
    if not actor_roles(request).intersection(roles):
        raise CoreAPIError("PERMISSION_DENIED", "Bạn không có quyền thực hiện thao tác này.", 403)


def is_teacher(actor, section, *, roles=()):
    if "TEACHER" not in roles:
        return False
    return ClassTeacher.objects.filter(
        class_section=section, user_id=actor.id, status="ACTIVE"
    ).exists()


def can_read(request, section):
    return (
        is_teacher(request.user, section, roles=actor_roles(request))
        or Enrollment.objects.filter(
            class_section=section, user_id=request.user.id, status="ACTIVE"
        ).exists()
        or "SYSTEM_ADMIN" in actor_roles(request)
    )


def require_read(request, section):
    if not can_read(request, section):
        raise CoreAPIError("RESOURCE_NOT_FOUND", "Không tìm thấy lớp học.", 404)


def require_manage(request, section, *, teacher_only=False):
    if not is_teacher(request.user, section, roles=actor_roles(request)) and (
        teacher_only or "SYSTEM_ADMIN" not in actor_roles(request)
    ):
        raise CoreAPIError("PERMISSION_DENIED", "Bạn không có quyền quản lý lớp học này.", 403)


def visible_courses(request):
    require_role(request, "STUDENT", "TEACHER", "SYSTEM_ADMIN")
    qs = Course.objects.all()
    if actor_roles(request).intersection({"TEACHER", "SYSTEM_ADMIN"}):
        return qs
    enrolled_courses = Enrollment.objects.filter(
        user_id=request.user.id,
        status="ACTIVE",
    ).values("class_section__course_id")
    return qs.filter(pk__in=enrolled_courses)


def visible_classes(request):
    qs = ClassSection.objects.all()
    if "SYSTEM_ADMIN" in actor_roles(request):
        return qs
    scope = Q(enrollments__user_id=request.user.id, enrollments__status="ACTIVE")
    if "TEACHER" in actor_roles(request):
        scope |= Q(teachers__user_id=request.user.id, teachers__status="ACTIVE")
    return qs.filter(scope).distinct()


def require_open(section, *, forming=False):
    if section.status != "OPEN":
        raise CoreAPIError(
            "CLASS_NOT_OPEN", "Lớp học hiện không mở để thực hiện thao tác này.", 409
        )
    if forming and section.grouping_phase != "FORMING":
        raise CoreAPIError(
            "GROUPING_LOCKED", "Lớp đã chốt nhóm; hãy liên hệ giảng viên phụ trách.", 409
        )
