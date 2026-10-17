from apps.courses.permissions import actor_roles, is_teacher, require_read, visible_classes
from apps.courses.serializers.classes import ClassSerializer, TeacherSerializer
from common.pagination import list_status, paginate


def list_classes(request):
    qs = visible_classes(request).select_related("course")
    status = list_status(request.query_params, {"OPEN", "CLOSED", "ARCHIVED"})
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={"actor": str(request.user.id), "resource": "classes", "status": status},
    )
    return ClassSerializer(rows, many=True).data, meta


def class_detail(request, section):
    require_read(request, section)
    return ClassSerializer(section).data


def class_teachers(request, section):
    require_read(request, section)
    active_only = not (is_teacher(request.user, section) or "SYSTEM_ADMIN" in actor_roles(request))
    status = list_status(request.query_params, {"ACTIVE", "LEFT"})
    qs = section.teachers.all()
    if active_only:
        qs = qs.filter(status="ACTIVE")
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "teachers",
            "status": status,
            "active_only": active_only,
        },
        time_field="assigned_at",
    )
    return TeacherSerializer(rows, many=True).data, meta
