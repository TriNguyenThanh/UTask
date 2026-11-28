from django.db.models import (
    Count,
    IntegerField,
    Manager,
    OuterRef,
    QuerySet,
    Subquery,
    UUIDField,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from apps.courses.filters import apply_filterset, list_status
from apps.courses.permissions import actor_roles, require_read, visible_classes
from apps.groups.filters import StudyGroupFilter
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.groups.permissions import active_enrollment, require_group_read
from apps.groups.queries.profiles import fetch_user_profiles
from apps.groups.serializers.groups import GroupSerializer, MyGroupSerializer, ProjectLinkSerializer
from apps.groups.serializers.members import MemberSerializer
from common.pagination import paginate


def annotate_groups(queryset):
    if not isinstance(queryset, QuerySet) or not isinstance(GroupMember.objects, Manager):
        return queryset
    member_count_subquery = (
        GroupMember.objects.filter(group_id=OuterRef("pk"), status="ACTIVE")
        .values("group_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    leader_id_subquery = GroupMember.objects.filter(
        group_id=OuterRef("pk"), status="ACTIVE", role="LEADER"
    ).values("enrollment__user_id")[:1]
    return queryset.annotate(
        _member_count=Coalesce(
            Subquery(member_count_subquery, output_field=IntegerField()), Value(0)
        ),
        _leader_id=Subquery(leader_id_subquery, output_field=UUIDField()),
    )


def list_groups(request, section):
    require_read(request, section)
    qs, filters = apply_filterset(
        StudyGroupFilter, request.query_params, StudyGroup.objects.filter(class_section=section)
    )
    qs = annotate_groups(qs)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "groups",
            **filters,
        },
    )
    return GroupSerializer(rows, many=True).data, meta


def visible_groups(request):
    qs, filters = apply_filterset(
        StudyGroupFilter,
        request.query_params,
        StudyGroup.objects.filter(class_section__in=visible_classes(request)),
    )
    qs = annotate_groups(qs)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={"actor": str(request.user.id), "resource": "groups", **filters},
    )
    return GroupSerializer(rows, many=True).data, meta


def my_class_group(request, section):
    require_read(request, section)
    enrollment = active_enrollment(section, request.user)
    membership = (
        GroupMember.objects.filter(
            class_section=section,
            enrollment=enrollment,
            status="ACTIVE",
            group__status="ACTIVE",
        )
        .select_related("group")
        .first()
    )
    if membership is None:
        return None
    group = membership.group
    members = list(
        GroupMember.objects.filter(group=group, status="ACTIVE")
        .select_related("enrollment")
        .order_by("role", "joined_at", "id")
    )
    if members:
        profiles = fetch_user_profiles([row.enrollment.user_id for row in members])
        for row in members:
            row.profile = profiles.get(str(row.enrollment.user_id), {})
    group._member_count = len(members)
    group._leader_id = next(
        (row.enrollment.user_id for row in members if row.role == "LEADER"), None
    )
    group.my_role = membership.role
    group._active_members = members
    return MyGroupSerializer(group).data


def group_detail(request, group_id):
    group = get_object_or_404(
        annotate_groups(StudyGroup.objects.select_related("class_section")), pk=group_id
    )
    require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
    return GroupSerializer(group).data


def group_members(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
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
        profiles = fetch_user_profiles([row.enrollment.user_id for row in rows])
        for row in rows:
            row.profile = profiles.get(str(row.enrollment.user_id), {})
    return MemberSerializer(rows, many=True).data, meta


def group_projects(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
    rows, meta = paginate(
        GroupProjectLink.objects.filter(group=group),
        request.query_params,
        scope={"actor": str(request.user.id), "group": str(group.pk), "resource": "projects"},
        time_field="linked_at",
    )
    return ProjectLinkSerializer(rows, many=True).data, meta
