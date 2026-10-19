from apps.courses.permissions import actor_roles, require_manage
from apps.groups.models import StudyGroup
from apps.groups.permissions import require_group_read
from apps.messaging.models import Activity
from apps.messaging.serializers.activities import ActivitySerializer
from common.pagination import paginate


def class_activities(request, section, group_id=None):
    qs = Activity.objects.filter(class_section=section)
    if group_id:
        from django.shortcuts import get_object_or_404

        group = get_object_or_404(StudyGroup, pk=group_id, class_section=section)
        require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
        qs = qs.filter(subject_type="StudyGroup", subject_id=group_id)
    else:
        require_manage(request, section)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "group": str(group_id) if group_id else None,
            "resource": "activities",
        },
    )
    return ActivitySerializer(rows, many=True).data, meta
