from rest_framework import serializers

from apps.courses.models import Course
from common.serializers import StrictInputSerializer


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "code", "name", "created_by_id", "archived_at"]
        read_only_fields = ["created_by_id"]


class CourseInputSerializer(StrictInputSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)

    def validate_code(self, value):
        return value.strip().upper()


class CoursePatchSerializer(CourseInputSerializer):
    code = serializers.CharField(max_length=50, required=False)
    name = serializers.CharField(max_length=200, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Cần cung cấp ít nhất một trường để cập nhật.")
        return attrs
