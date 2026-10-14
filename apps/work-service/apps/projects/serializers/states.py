import math

from rest_framework import serializers

from apps.projects.models import State
from common.serializers import StrictInputSerializer


class StateSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = State
        fields = [
            "id",
            "project_id",
            "name",
            "slug",
            "color",
            "sequence",
            "group",
            "is_default",
            "created_at",
        ]


class CreateStateSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=50)
    color = serializers.RegexField(
        r"^#[0-9A-Fa-f]{6}$",
        max_length=7,
        error_messages={"invalid": "Mã màu phải gồm dấu # và 6 ký tự từ 0–9 hoặc A–F."},
    )
    sequence = serializers.FloatField()
    group = serializers.ChoiceField(choices=State.Group.choices)

    def validate_sequence(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError("Thứ tự cột trạng thái phải là số hợp lệ.")
        return value


class PatchStateSerializer(CreateStateSerializer):
    name = serializers.CharField(max_length=50, required=False)
    color = serializers.RegexField(
        r"^#[0-9A-Fa-f]{6}$",
        max_length=7,
        required=False,
        error_messages={"invalid": "Mã màu phải gồm dấu # và 6 ký tự từ 0–9 hoặc A–F."},
    )
    sequence = serializers.FloatField(required=False)
    group = serializers.ChoiceField(choices=State.Group.choices, required=False)
    is_default = serializers.BooleanField(required=False)


class DeleteStateSerializer(serializers.Serializer):
    deleted_state_id = serializers.UUIDField()
    migrated_tasks_count = serializers.IntegerField()
    target_state_id = serializers.UUIDField(allow_null=True)


class DeleteStateInputSerializer(StrictInputSerializer):
    target_state_id = serializers.UUIDField(required=False, allow_null=True)
