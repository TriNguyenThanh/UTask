from rest_framework import serializers

from apps.courses.models import Enrollment
from common.serializers import StrictInputSerializer


class JoinCodeSerializer(StrictInputSerializer):
    code = serializers.CharField(max_length=100)


class StudentListSerializer(StrictInputSerializer):
    students = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=100,
        error_messages={
            "min_length": "Danh sách phải có ít nhất 1 sinh viên.",
            "max_length": "Mỗi yêu cầu chỉ được chứa tối đa 100 sinh viên.",
        },
    )


class EnrollmentSerializer(serializers.ModelSerializer):
    profile = serializers.DictField(read_only=True, required=False)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "class_section_id",
            "user_id",
            "status",
            "source",
            "enrolled_at",
            "left_at",
            "profile",
        ]


class EnrollmentSummarySerializer(serializers.Serializer):
    total_records = serializers.IntegerField()
    enrolled = serializers.IntegerField()
    already_enrolled = serializers.IntegerField()
    failed = serializers.IntegerField()
    created_accounts = serializers.IntegerField()
    existing_accounts = serializers.IntegerField()
    flagged = serializers.IntegerField()
    duplicates = serializers.IntegerField()


class StudentListResultSerializer(serializers.Serializer):
    summary = EnrollmentSummarySerializer()
    results = serializers.ListField(child=serializers.DictField())


class EnrollmentExitSerializer(StrictInputSerializer):
    reason = serializers.CharField(max_length=500)
