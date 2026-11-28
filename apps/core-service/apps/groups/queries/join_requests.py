from django.shortcuts import get_object_or_404

from apps.courses.filters import list_status
from apps.courses.permissions import actor_roles, require_read
from apps.groups.models import GroupJoinRequest, StudyGroup
from apps.groups.permissions import active_enrollment, require_group_read, require_leader
from apps.groups.queries.profiles import fetch_user_profiles
from apps.groups.serializers.join_requests import (
    JOIN_REQUEST_STATUS_CHOICES,
    GroupJoinRequestSerializer,
)
from apps.groups.serializers.validators import build_minimal_profile
from common.pagination import paginate


def list_group_join_requests(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    roles = actor_roles(request)
    require_group_read(group, request.user, roles=roles, admin_allowed=True)
    require_leader(group, request.user, teacher_allowed=True, roles=roles, admin_allowed=True)
    status = list_status(request.query_params, set(JOIN_REQUEST_STATUS_CHOICES))
    qs = GroupJoinRequest.objects.filter(group=group).select_related("group")
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "group": str(group.pk),
            "resource": "join-requests",
            "status": status,
        },
    )
    profiles = fetch_user_profiles([row.user_id for row in rows])
    for row in rows:
        row.requester_profile = build_minimal_profile(row.user_id, profiles.get(str(row.user_id)))
    return GroupJoinRequestSerializer(rows, many=True).data, meta


def list_my_join_requests(request, section):
    require_read(request, section)
    enrollment = active_enrollment(section, request.user)
    status = list_status(request.query_params, set(JOIN_REQUEST_STATUS_CHOICES))
    qs = GroupJoinRequest.objects.filter(
        class_section=section, enrollment=enrollment
    ).select_related("group")
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "my-join-requests",
            "status": status,
        },
    )
    profiles = fetch_user_profiles([request.user.id] if rows else [])
    actor_profile = build_minimal_profile(request.user.id, profiles.get(str(request.user.id)))
    for row in rows:
        row.requester_profile = actor_profile
    return GroupJoinRequestSerializer(rows, many=True).data, meta
