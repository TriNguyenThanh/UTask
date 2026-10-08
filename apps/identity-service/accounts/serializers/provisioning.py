from rest_framework import serializers

from accounts.models import User
from common.serializers import StrictInputMixin


class StudentRowSerializer(StrictInputMixin, serializers.Serializer):
    row_number = serializers.IntegerField(min_value=1)
    email = serializers.EmailField(max_length=255, required=False, allow_blank=True)
    student_id = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )
    first_name = serializers.CharField(max_length=100, default="", allow_blank=True)
    last_name = serializers.CharField(max_length=100, default="", allow_blank=True)

    def validate(self, attrs):
        attrs["email"] = User.objects.normalize_email(attrs.get("email", ""))
        attrs["student_id"] = User.objects.normalize_student_id(attrs.get("student_id"))
        if not attrs["email"] and not attrs["student_id"]:
            raise serializers.ValidationError("An email or student_id is required.")
        return attrs


class ProvisionStudentsSerializer(StrictInputMixin, serializers.Serializer):
    # Per-row validation is intentional: a bad row must not discard valid classmates.
    students = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)
