from apps.courses.models import Enrollment
from apps.courses.permissions import bearer, require_manage
from apps.courses.serializers.enrollments import EnrollmentSerializer
from common.errors import ClassroomError
from common.pagination import list_status, paginate
from infrastructure.identity import IdentityClient


def list_enrollments(request, section):
    require_manage(request, section)
    status = list_status(request.query_params, {"ACTIVE", "LEFT", "REMOVED"})
    qs = Enrollment.objects.filter(class_section=section)
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "enrollments",
            "status": status,
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
