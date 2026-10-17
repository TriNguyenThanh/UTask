from uuid import UUID

from rest_framework import serializers

from apps.projects.models import Project
from common.serializers import ListMetaSerializer, StrictInputSerializer


class ProjectListScopeSerializer(serializers.Serializer):
    partial = serializers.BooleanField()
    source = serializers.ChoiceField(choices=["WORK_MEMBERSHIP"])
    teacher_scope = serializers.ChoiceField(choices=["UNAVAILABLE"])


class ProjectListMetaSerializer(ListMetaSerializer):
    scope = ProjectListScopeSerializer(required=False)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "identifier",
            "name",
            "description",
            "target_goals",
            "tech_stack",
            "start_date",
            "end_date",
            "classroom_group_id",
            "class_id",
            "group_source_version",
            "version",
            "board_revision",
            "github_repo_name",
            "github_repo_id",
            "github_connection_status",
            "github_synced_at",
            "created_at",
            "updated_at",
            "archived_at",
        ]


class CreateProjectSerializer(StrictInputSerializer):
    identifier = serializers.RegexField(
        r"^[A-Z0-9]{2,10}$",
        max_length=10,
        error_messages={"invalid": "Mã dự án phải có từ 2 đến 10 chữ cái viết hoa hoặc chữ số."},
    )
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    target_goals = serializers.CharField(required=False, allow_blank=True, default="")
    tech_stack = serializers.DictField(required=False, default=dict)
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    classroom_group_id = serializers.CharField(max_length=100)

    def validate_classroom_group_id(self, value):
        try:
            return str(UUID(value))
        except ValueError:
            # Developer adapters retain their logical string IDs; the remote
            # authority adapter validates UUIDs before making an HTTP request.
            return value

    def validate(self, attrs):
        if (
            attrs.get("start_date")
            and attrs.get("end_date")
            and attrs["end_date"] < attrs["start_date"]
        ):
            raise serializers.ValidationError(
                {"end_date": "Ngày kết thúc không được diễn ra trước ngày bắt đầu."}
            )
        return attrs


class PatchProjectSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    target_goals = serializers.CharField(required=False, allow_blank=True)
    tech_stack = serializers.DictField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=0)


class VersionSerializer(StrictInputSerializer):
    expected_version = serializers.IntegerField(min_value=0)
