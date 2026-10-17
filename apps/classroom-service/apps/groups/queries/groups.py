from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.courses.permissions import bearer, require_read
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.groups.permissions import require_group_read
from apps.groups.serializers.groups import GroupSerializer, ProjectLinkSerializer
from apps.groups.serializers.members import MemberSerializer
from common.errors import ClassroomError
from common.pagination import list_status, paginate
from infrastructure.identity import IdentityClient


def list_groups(request, section):
    require_read(request, section)
    qs = StudyGroup.objects.filter(class_section=section)
    status = list_status(request.query_params, {"ACTIVE", "ARCHIVED"})
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "groups",
            "status": status,
        },
    )
    return GroupSerializer(rows, many=True).data, meta


def visible_groups(request):
    qs = StudyGroup.objects.filter(
        Q(
            class_section__teachers__user_id=request.user.id,
            class_section__teachers__status="ACTIVE",
        )
        | Q(
            class_section__enrollments__user_id=request.user.id,
            class_section__enrollments__status="ACTIVE",
        )
    ).distinct()
    status = list_status(request.query_params, {"ACTIVE", "ARCHIVED"})
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={"actor": str(request.user.id), "resource": "groups", "status": status},
    )
    return GroupSerializer(rows, many=True).data, meta


def group_detail(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_read(request, group.class_section)
    return GroupSerializer(group).data


def group_members(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_group_read(group, request.user)
    status = list_status(request.query_params, {"ACTIVE", "LEFT", "REMOVED"})
    qs = GroupMember.objects.filter(group=group).select_related("enrollment")
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "group": str(group.pk),
            "resource": "members",
            "status": status,
        },
        time_field="joined_at",
    )
    if rows:
        try:
            profiles = {
                item["id"]: item
                for item in IdentityClient().users(
                    bearer(request), [row.enrollment.user_id for row in rows]
                )
            }
        except ClassroomError:
            profiles = {}
        for row in rows:
            row.profile = profiles.get(str(row.enrollment.user_id), {})
    return MemberSerializer(rows, many=True).data, meta


def group_projects(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_group_read(group, request.user)
    rows, meta = paginate(
        GroupProjectLink.objects.filter(group=group),
        request.query_params,
        scope={"actor": str(request.user.id), "group": str(group.pk), "resource": "projects"},
        time_field="linked_at",
    )
    return ProjectLinkSerializer(rows, many=True).data, meta
