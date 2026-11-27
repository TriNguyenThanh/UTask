from collections import defaultdict

from django.db.models import Count, Exists, OuterRef, Q

from apps.courses.models import ClassSection, Enrollment
from apps.courses.permissions import actor_roles, require_manage, require_read
from apps.courses.serializers.classes import ClassSummarySerializer
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from common.errors import ClassroomError
from common.pagination import list_status


def _build_class_summaries(sections):
    if not sections:
        return []
    class_ids = [section.pk for section in sections]
    enrolled_counts = dict(
        Enrollment.objects.filter(class_section_id__in=class_ids, status="ACTIVE")
        .values("class_section_id")
        .annotate(total=Count("pk"))
        .values_list("class_section_id", "total")
    )
    in_active_group = GroupMember.objects.filter(
        enrollment_id=OuterRef("pk"),
        status="ACTIVE",
        group__status="ACTIVE",
    )
    unassigned_counts = dict(
        Enrollment.objects.filter(class_section_id__in=class_ids, status="ACTIVE")
        .annotate(_has_active_group=Exists(in_active_group))
        .filter(_has_active_group=False)
        .values("class_section_id")
        .annotate(total=Count("pk"))
        .values_list("class_section_id", "total")
    )
    has_project_link = GroupProjectLink.objects.filter(group_id=OuterRef("pk"))
    group_rows = (
        StudyGroup.objects.filter(class_section_id__in=class_ids, status="ACTIVE")
        .annotate(
            active_members=Count(
                "members",
                filter=Q(members__status="ACTIVE", members__enrollment__status="ACTIVE"),
            ),
            has_project=Exists(has_project_link),
        )
        .values("id", "class_section_id", "active_members", "has_project")
        .order_by("id")
    )
    groups_by_class = defaultdict(list)
    for row in group_rows:
        groups_by_class[row["class_section_id"]].append(row)

    summaries = []
    for section in sections:
        groups = groups_by_class[section.pk]
        summaries.append(
            {
                "class_id": section.pk,
                "code": section.code,
                "name": section.name,
                "term": section.term,
                "status": section.status,
                "grouping_phase": section.grouping_phase,
                "group_min_size": section.group_min_size,
                "group_max_size": section.group_max_size,
                "course_summary": {
                    "id": section.course_id,
                    "code": section.course.code,
                    "name": section.course.name,
                },
                "enrolled_active_count": enrolled_counts.get(section.pk, 0),
                "active_group_count": len(groups),
                "students_without_team_count": unassigned_counts.get(section.pk, 0),
                "groups_below_min_size_count": sum(
                    1 for g in groups if g["active_members"] < section.group_min_size
                ),
                "groups_without_project_count": sum(1 for g in groups if not g["has_project"]),
                "group_ids": [str(g["id"]) for g in groups],
            }
        )
    return summaries


def class_summary(request, section):
    require_read(request, section)
    require_manage(request, section)
    hydrated = ClassSection.objects.select_related("course").get(pk=section.pk)
    payload = _build_class_summaries([hydrated])[0]
    return ClassSummarySerializer(payload).data


def teacher_classes_summary(request):
    roles = actor_roles(request)
    if "TEACHER" in roles:
        qs = ClassSection.objects.filter(
            teachers__user_id=request.user.id,
            teachers__status="ACTIVE",
        ).distinct()
    elif "SYSTEM_ADMIN" in roles:
        qs = ClassSection.objects.all()
    else:
        raise ClassroomError(
            "PERMISSION_DENIED",
            "Bạn không có quyền xem thống kê lớp học dành cho giảng viên.",
            403,
        )
    status = list_status(request.query_params, {"OPEN", "CLOSED", "ARCHIVED"})
    if status is not None:
        qs = qs.filter(status=status)
    sections = list(qs.select_related("course").order_by("-created_at", "-id"))
    payload = _build_class_summaries(sections)
    return ClassSummarySerializer(payload, many=True).data
