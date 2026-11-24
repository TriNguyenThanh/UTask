from apps.courses.filters import EnrollmentFilter
from apps.courses.models import Enrollment
from apps.courses.permissions import bearer, require_manage
from apps.courses.serializers.enrollments import EnrollmentSerializer
from common.errors import ClassroomError
from common.filters import apply_filterset
from common.pagination import paginate
from infrastructure.identity import IdentityClient


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
        try:
            profiles = {
                item["id"]: item
                for item in IdentityClient().users(bearer(request), [row.user_id for row in rows])
            }
        except ClassroomError:
            profiles = {}
        for row in rows:
            row.profile = profiles.get(str(row.user_id), {})
    return EnrollmentSerializer(rows, many=True).data, meta
