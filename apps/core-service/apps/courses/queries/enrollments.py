from apps.courses.filters import EnrollmentFilter, apply_filterset
from apps.courses.models import Enrollment
from apps.courses.permissions import require_manage
from apps.courses.serializers.enrollments import EnrollmentSerializer
from apps.groups.queries.profiles import fetch_user_profiles
from common.pagination import paginate


def list_enrollments(request, section):
    require_manage(request, section)
    qs, filters = apply_filterset(
        EnrollmentFilter, request.query_params, Enrollment.objects.filter(class_section=section)
    )
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "enrollments",
            **filters,
        },
        time_field="enrolled_at",
    )
    if rows:
        profiles = fetch_user_profiles([row.user_id for row in rows])
        for row in rows:
            row.profile = profiles.get(str(row.user_id), {})
    return EnrollmentSerializer(rows, many=True).data, meta
