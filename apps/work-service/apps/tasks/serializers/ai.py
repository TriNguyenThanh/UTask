from rest_framework import serializers

from apps.tasks.models import Task
from apps.tasks.serializers import CreateTaskSerializer, SubtaskSerializer
from common.serializers import StrictInputSerializer


class BacklogItemSerializer(CreateTaskSerializer):
    local_id = serializers.CharField(max_length=100)
    ai_revision = serializers.CharField(max_length=100)
    dependencies = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        max_length=100,
        error_messages={"max_length": "Danh sách công việc phụ thuộc không được vượt quá 100 mục."},
    )


class SubtaskItemSerializer(SubtaskSerializer):
    local_id = serializers.CharField(max_length=100)
    ai_revision = serializers.CharField(max_length=100)
    dependencies = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        max_length=100,
        error_messages={"max_length": "Danh sách công việc phụ thuộc không được vượt quá 100 mục."},
    )


class BacklogApplySerializer(StrictInputSerializer):
    proposal_id = serializers.CharField(max_length=100)
    context_version = serializers.IntegerField(min_value=0)
    expected_project_version = serializers.IntegerField(min_value=1)
    tasks = BacklogItemSerializer(
        many=True,
        allow_empty=False,
        max_length=100,
        error_messages={
            "empty": "Vui lòng chọn ít nhất một công việc trong đề xuất.",
            "max_length": "Mỗi lần áp dụng đề xuất chỉ được tạo tối đa 100 công việc.",
        },
    )


class SubtaskApplySerializer(StrictInputSerializer):
    proposal_id = serializers.CharField(max_length=100)
    context_version = serializers.IntegerField(min_value=0)
    expected_parent_version = serializers.IntegerField(min_value=1)
    subtasks = SubtaskItemSerializer(
        many=True,
        allow_empty=False,
        max_length=100,
        error_messages={
            "empty": "Vui lòng chọn ít nhất một công việc con trong đề xuất.",
            "max_length": "Mỗi lần áp dụng đề xuất chỉ được tạo tối đa 100 công việc con.",
        },
    )


class AppliedTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    local_id = serializers.CharField()
    code = serializers.CharField()
    version = serializers.IntegerField()
    ai_revision = serializers.CharField()
    approved_payload_hash = serializers.CharField()


class ApplyResultSerializer(serializers.Serializer):
    operation_id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    parent_task_id = serializers.UUIDField(allow_null=True)
    proposal_id = serializers.CharField()
    source = serializers.CharField()
    created_count = serializers.IntegerField()
    affected_tasks = AppliedTaskSerializer(many=True)
    committed_at = serializers.DateTimeField()


class ApprovedActionSerializer(StrictInputSerializer):
    kind = serializers.ChoiceField(
        choices=["SET_DEADLINE", "SET_PRIORITY", "SET_ASSIGNEES", "SPRINT_SCOPE"]
    )
    task_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách người phụ trách không được vượt quá 100 mục."},
    )
    sprint_id = serializers.UUIDField(required=False)
    scope_action = serializers.ChoiceField(choices=["ADD", "REMOVE"], required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    expected_sprint_version = serializers.IntegerField(required=False, min_value=1)

    def validate(self, data):
        required = {
            "SET_DEADLINE": {"due_date"},
            "SET_PRIORITY": {"priority"},
            "SET_ASSIGNEES": {"assignee_ids"},
            "SPRINT_SCOPE": {"sprint_id", "scope_action", "reason", "expected_sprint_version"},
        }[data["kind"]]
        common = {"kind", "task_id", "expected_version"}
        if not required <= set(data) or set(data) - common - required:
            raise serializers.ValidationError(
                "Hành động thiếu trường dữ liệu bắt buộc hoặc chứa trường dữ liệu "
                "không được hỗ trợ."
            )
        return data


class ActionApplySerializer(StrictInputSerializer):
    proposal_id = serializers.CharField(max_length=100)
    item_id = serializers.CharField(max_length=100)
    ai_revision = serializers.CharField(max_length=100)
    context_version = serializers.IntegerField(min_value=0)
    actions = ApprovedActionSerializer(
        many=True,
        allow_empty=False,
        max_length=100,
        error_messages={
            "empty": "Vui lòng chọn ít nhất một thay đổi trong đề xuất.",
            "max_length": "Mỗi lần áp dụng đề xuất chỉ được thực hiện tối đa 100 thay đổi.",
        },
    )
