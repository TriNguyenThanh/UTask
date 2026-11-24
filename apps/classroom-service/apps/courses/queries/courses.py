from apps.courses.permissions import visible_courses
from apps.courses.serializers.courses import CourseSerializer


def list_courses(request):
    return CourseSerializer(visible_courses(request).order_by("code", "id"), many=True).data
