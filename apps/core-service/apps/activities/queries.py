from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.activities.filters import ClassroomActivityFilter
from apps.activities.models import ClassroomActivity
from apps.activities.serializers import ClassroomActivitySerializer
from apps.courses.filters import apply_filterset
from apps.courses.permissions import actor_roles, require_manage
from apps.groups.models import GroupJoinRequest, GroupMember, GroupTopicProposal, StudyGroup
from apps.groups.permissions import require_group_read
from common.pagination import paginate


def class_activities(request, section, group_id=None):
    qs = ClassroomActivity.objects.filter(class_section=section)
    if group_id:
        group = get_object_or_404(StudyGroup, pk=group_id, class_section=section)
        require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
        qs = qs.filter(
            Q(subject_type="StudyGroup", subject_id=group_id)
            | Q(
                subject_type="GroupMember",
                subject_id__in=GroupMember.objects.filter(group_id=group_id).values("pk"),
            )
            | Q(
                subject_type="GroupJoinRequest",
                subject_id__in=GroupJoinRequest.objects.filter(group_id=group_id).values("pk"),
            )
            | Q(
                subject_type="GroupTopicProposal",
                subject_id__in=GroupTopicProposal.objects.filter(group_id=group_id).values("pk"),
            )
        )
    else:
        require_manage(request, section)
    qs, filters = apply_filterset(ClassroomActivityFilter, request.query_params, qs)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "group": str(group_id) if group_id else None,
            "resource": "activities",
            **filters,
        },
        salt="classroom-list-v1",
    )
    return ClassroomActivitySerializer(rows, many=True).data, meta
