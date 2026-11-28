from django.shortcuts import get_object_or_404

from apps.courses.filters import CourseFilter, apply_filterset
from apps.courses.permissions import visible_courses
from apps.courses.serializers.courses import CourseSerializer


def list_courses(request):
    qs, _ = apply_filterset(CourseFilter, request.query_params, visible_courses(request))
    return CourseSerializer(qs.order_by("code", "id"), many=True).data


def course_detail(request, course_id):
    course = get_object_or_404(visible_courses(request), pk=course_id)
    return CourseSerializer(course).data
