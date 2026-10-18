from rest_framework import serializers

from apps.courses.models import Course
from common.serializers import StrictInputSerializer


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "code", "name", "archived_at"]


class CourseInputSerializer(StrictInputSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)

    def validate_code(self, value):
        return value.strip().upper()
