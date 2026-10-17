from rest_framework import serializers

from apps.courses.models import ClassSection, ClassTeacher
from common.serializers import StrictInputSerializer


class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassSection
        exclude = ["join_code_hash"]


class ClassInputSerializer(StrictInputSerializer):
    course_id = serializers.UUIDField()
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    term = serializers.CharField(max_length=100)
    starts_on = serializers.DateField()
    ends_on = serializers.DateField()
    group_min_size = serializers.IntegerField(min_value=1, default=1)
    group_max_size = serializers.IntegerField(min_value=1, default=6)
    primary_teacher_id = serializers.UUIDField(required=False)

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if (
            attrs["starts_on"] > attrs["ends_on"]
            or attrs["group_min_size"] > attrs["group_max_size"]
        ):
            raise serializers.ValidationError("Ngày học hoặc giới hạn thành viên không hợp lệ.")
        return attrs


class ClassPatchSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False)
    term = serializers.CharField(max_length=100, required=False)
    starts_on = serializers.DateField(required=False)
    ends_on = serializers.DateField(required=False)
    group_min_size = serializers.IntegerField(min_value=1, required=False)
    group_max_size = serializers.IntegerField(min_value=1, required=False)


class VersionSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)


class ClassStateSerializer(VersionSerializer):
    status = serializers.ChoiceField(choices=["OPEN", "CLOSED", "ARCHIVED"])


class CodeInputSerializer(VersionSerializer):
    expires_at = serializers.DateTimeField(required=False)
    enabled = serializers.BooleanField(default=True)


class AccessCodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    code = serializers.CharField(required=False)
    expires_at = serializers.DateTimeField(allow_null=True)
    enabled = serializers.BooleanField()


class TeacherInputSerializer(VersionSerializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["PRIMARY", "CO_TEACHER"], default="CO_TEACHER")
    status = serializers.ChoiceField(choices=["ACTIVE", "LEFT"], default="ACTIVE")


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassTeacher
        fields = ["id", "user_id", "role", "status", "assigned_at", "left_at"]
