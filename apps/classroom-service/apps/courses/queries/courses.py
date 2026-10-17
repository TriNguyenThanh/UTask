from apps.courses.models import Course
from apps.courses.permissions import require_role
from apps.courses.serializers.courses import CourseSerializer


def list_courses(request):
    require_role(request, "STUDENT", "TEACHER", "SYSTEM_ADMIN")
    return CourseSerializer(Course.objects.order_by("code", "id"), many=True).data
