from rest_framework import serializers

from apps.tasks.models import Epic, Label
from common.serializers import StrictInputSerializer


class LabelSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Label
        fields = ["id", "project_id", "name", "color", "description", "created_at", "deleted_at"]


class EpicSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Epic
        fields = [
            "id",
            "project_id",
            "name",
            "description",
            "lead_user_id",
            "status",
            "start_date",
            "target_date",
            "created_at",
            "updated_at",
            "deleted_at",
        ]


class LabelInputSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=50)
    color = serializers.RegexField(
        r"^#[0-9A-Fa-f]{6}$",
        error_messages={"invalid": "Màu nhãn phải gồm dấu # và 6 ký tự thập lục phân (0–9, A–F)."},
    )
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=10000
    )


class EpicInputSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    lead_user_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Epic.Status.choices, required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    target_date = serializers.DateField(required=False, allow_null=True)


class DeletedLabelSerializer(serializers.Serializer):
    deleted_label_id = serializers.UUIDField()


class DeletedEpicSerializer(serializers.Serializer):
    deleted_epic_id = serializers.UUIDField()


class TaskLabelsSerializer(StrictInputSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=["ADD", "REMOVE"])
    label_ids = serializers.ListField(
        child=serializers.UUIDField(),
        max_length=100,
        allow_empty=False,
        error_messages={
            "max_length": "Danh sách nhãn không được vượt quá 100 mục.",
            "empty": "Vui lòng chọn ít nhất một nhãn.",
        },
    )
