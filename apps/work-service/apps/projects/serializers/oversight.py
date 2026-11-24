from rest_framework import serializers

from apps.projects.metrics import SIGNAL_CODES, SIGNAL_SEVERITIES
from common.serializers import StrictInputSerializer


class OversightQuerySerializer(StrictInputSerializer):
    class_id = serializers.CharField(required=False, max_length=100, allow_blank=False)
    classroom_group_ids = serializers.CharField(required=False, max_length=5000, allow_blank=False)
    inactive_days = serializers.IntegerField(min_value=1, max_value=90, default=7)
    include_archived = serializers.BooleanField(required=False, default=False)

    def validate_classroom_group_ids(self, value):
        raw_items = [item.strip() for item in value.split(",")]
        if not raw_items or any(not item for item in raw_items):
            raise serializers.ValidationError(
                "Danh sách mã nhóm học tập chứa giá trị trống không hợp lệ."
            )
        unique_items = list(dict.fromkeys(raw_items))
        if len(unique_items) > 100:
            raise serializers.ValidationError(
                "Danh sách mã nhóm học tập không được vượt quá 100 mục."
            )
        if any(len(item) > 100 for item in unique_items):
            raise serializers.ValidationError("Mã nhóm học tập không hợp lệ.")
        return unique_items


class OversightProgressSerializer(serializers.Serializer):
    total_tasks = serializers.IntegerField(min_value=0, read_only=True)
    completed_tasks = serializers.IntegerField(min_value=0, read_only=True)
    completion_rate = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
        coerce_to_string=False,
        read_only=True,
    )
    total_points = serializers.IntegerField(min_value=0, read_only=True)
    completed_points = serializers.IntegerField(min_value=0, read_only=True)


class OversightSignalSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=list(SIGNAL_CODES), read_only=True)
    severity = serializers.ChoiceField(choices=list(SIGNAL_SEVERITIES), read_only=True)
    message = serializers.CharField(read_only=True)


class OversightActiveSprintSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    start_date = serializers.DateField(allow_null=True, read_only=True)
    end_date = serializers.DateField(allow_null=True, read_only=True)
    total_tasks = serializers.IntegerField(min_value=0, read_only=True)
    completed_tasks = serializers.IntegerField(min_value=0, read_only=True)


class OversightProjectSerializer(serializers.Serializer):
    project_id = serializers.UUIDField(read_only=True)
    identifier = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    classroom_class_id = serializers.CharField(allow_null=True, read_only=True)
    classroom_group_id = serializers.CharField(read_only=True)
    archived_at = serializers.DateTimeField(allow_null=True, read_only=True)
    progress = OversightProgressSerializer(read_only=True)
    overdue_count = serializers.IntegerField(min_value=0, read_only=True)
    blocked_count = serializers.IntegerField(min_value=0, read_only=True)
    unassigned_count = serializers.IntegerField(min_value=0, read_only=True)
    last_activity_at = serializers.DateTimeField(allow_null=True, read_only=True)
    active_sprint = OversightActiveSprintSerializer(allow_null=True, read_only=True)
    signals = OversightSignalSerializer(many=True, read_only=True)


class OversightSummarySerializer(serializers.Serializer):
    formula_version = serializers.CharField(read_only=True)
    business_date = serializers.DateField(read_only=True)
    inactive_days = serializers.IntegerField(min_value=1, read_only=True)
    total_projects = serializers.IntegerField(min_value=0, read_only=True)
    projects_with_signals = serializers.IntegerField(min_value=0, read_only=True)
    total_overdue_tasks = serializers.IntegerField(min_value=0, read_only=True)
    total_blocked_tasks = serializers.IntegerField(min_value=0, read_only=True)
    inactive_projects = serializers.IntegerField(min_value=0, read_only=True)
    average_completion_rate = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
        coerce_to_string=False,
        read_only=True,
    )


class TeacherOversightSerializer(serializers.Serializer):
    summary = OversightSummarySerializer(read_only=True)
    projects = OversightProjectSerializer(many=True, read_only=True)
