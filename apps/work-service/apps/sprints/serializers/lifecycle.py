from rest_framework import serializers

from apps.sprints.models import Sprint
from common.serializers import StrictInputSerializer


class SprintSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Sprint
        fields = [
            "id",
            "project_id",
            "name",
            "goal",
            "status",
            "start_date",
            "end_date",
            "sort_order",
            "version",
            "started_at",
            "closed_at",
            "created_at",
            "updated_at",
            "archived_at",
        ]


class CreateSprintSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=200)
    goal = serializers.CharField(required=False, default="", allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    end_date = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if (
            attrs.get("start_date")
            and attrs.get("end_date")
            and attrs["start_date"] > attrs["end_date"]
        ):
            raise serializers.ValidationError(
                {"end_date": "Ngày kết thúc không được diễn ra trước ngày bắt đầu."}
            )
        return attrs


class PatchSprintSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=200, required=False)
    goal = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=1)


class StartSprintSerializer(StrictInputSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class ScopeSerializer(StartSprintSerializer):
    action = serializers.ChoiceField(choices=["ADD", "REMOVE"])
    task_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=500)
    scope_change_reason = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class CloseSprintSerializer(StartSprintSerializer):
    target_sprint_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class ScopeResultSerializer(serializers.Serializer):
    sprint_id = serializers.UUIDField()
    modified_task_ids = serializers.ListField(child=serializers.UUIDField())
    is_scope_creep = serializers.BooleanField()
    version = serializers.IntegerField()


class CloseResultSerializer(serializers.Serializer):
    sprint_id = serializers.UUIDField()
    status = serializers.CharField()
    closed_at = serializers.DateTimeField()
    snapshot_version = serializers.IntegerField()
    target_sprint_id = serializers.UUIDField(allow_null=True)
    summary = serializers.DictField(child=serializers.IntegerField())
