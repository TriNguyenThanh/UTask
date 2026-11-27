from uuid import UUID

from rest_framework import serializers

from apps.tasks.models import Task
from common.serializers import StrictInputSerializer


class BoardFilterSerializer(StrictInputSerializer):
    sprint_id = serializers.CharField(required=False, max_length=100)
    assignee_id = serializers.UUIDField(required=False)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    is_blocked = serializers.BooleanField(required=False)
    epic_id = serializers.UUIDField(required=False)
    label_id = serializers.UUIDField(required=False)
    type = serializers.ChoiceField(choices=Task.Type.choices, required=False)
    search = serializers.CharField(required=False, max_length=200, allow_blank=False)
    include_subtasks = serializers.BooleanField(required=False)
    limit_per_column = serializers.IntegerField(min_value=1, max_value=100, default=50)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=50)
    cursor = serializers.CharField(required=False, max_length=4096)

    def validate_sprint_id(self, value):
        if value == "none":
            return value
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise serializers.ValidationError(
                "Mã chu kỳ làm việc phải là định danh hợp lệ (UUID) hoặc giá trị none."
            ) from exc


class BoardCardAssigneeSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    avatar_url = serializers.CharField(allow_null=True, read_only=True)


class BoardCardLabelSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)


class BoardCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    title = serializers.CharField()
    type = serializers.ChoiceField(choices=Task.Type.choices)
    priority = serializers.ChoiceField(choices=Task.Priority.choices)
    story_points = serializers.IntegerField(allow_null=True)
    due_date = serializers.DateField(allow_null=True)
    is_blocked = serializers.BooleanField()
    blocked_reason = serializers.CharField(allow_null=True)
    epic_id = serializers.UUIDField(allow_null=True)
    parent_id = serializers.UUIDField(allow_null=True)
    sort_order = serializers.FloatField()
    version = serializers.IntegerField()
    assignees = BoardCardAssigneeSerializer(many=True)
    labels = BoardCardLabelSerializer(many=True)
    subtasks_count = serializers.IntegerField(min_value=0)
    comments_count = serializers.IntegerField(min_value=0)
    attachments_count = serializers.IntegerField(min_value=0)
    has_pull_request = serializers.BooleanField()


class BoardColumnSerializer(serializers.Serializer):
    state_id = serializers.UUIDField()
    state_name = serializers.CharField()
    state_group = serializers.CharField()
    sequence = serializers.FloatField()
    column_total_tasks = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_cursor = serializers.CharField(allow_null=True)
    tasks = BoardCardSerializer(many=True)


class BoardSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    board_revision = serializers.IntegerField()
    columns = BoardColumnSerializer(many=True)
    total_columns = serializers.IntegerField()
    total_tasks = serializers.IntegerField()


class BoardColumnPageSerializer(BoardColumnSerializer):
    project_id = serializers.UUIDField()
    board_revision = serializers.IntegerField()
