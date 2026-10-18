from django.db.models import Q

from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient


def bearer(request):
    parts = request.headers.get("Authorization", "").split()
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else ""


def actor_roles(request):
    if not hasattr(request, "classroom_roles"):
        data = IdentityClient().current_user(bearer(request))
        if str(data["id"]) != str(request.user.id):
            raise ClassroomError(
                "AUTHENTICATION_REQUIRED", "Không thể xác minh tài khoản hiện tại.", 401
            )
        request.classroom_roles = set(data["roles"])
    return request.classroom_roles


def require_role(request, *roles):
    if not actor_roles(request).intersection(roles):
        raise ClassroomError("PERMISSION_DENIED", "Bạn không có quyền thực hiện thao tác này.", 403)


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
        raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy lớp học.", 404)


def require_manage(request, section, *, teacher_only=False):
    if not is_teacher(request.user, section, roles=actor_roles(request)) and (
        teacher_only or "SYSTEM_ADMIN" not in actor_roles(request)
    ):
        raise ClassroomError("PERMISSION_DENIED", "Bạn không có quyền quản lý lớp học này.", 403)


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
        raise ClassroomError(
            "CLASS_NOT_OPEN", "Lớp học hiện không mở để thực hiện thao tác này.", 409
        )
    if forming and section.grouping_phase != "FORMING":
        raise ClassroomError(
            "GROUPING_LOCKED", "Lớp đã chốt nhóm; hãy liên hệ giảng viên phụ trách.", 409
        )
