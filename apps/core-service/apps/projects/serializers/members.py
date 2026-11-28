from rest_framework import serializers

from apps.projects.models import ProjectMember
from common.serializers import StrictInputSerializer


class CapacitySerializer(StrictInputSerializer):
    weekly_capacity = serializers.IntegerField(min_value=0, max_value=2147483647)


class MemberSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True, default="")
    avatar_url = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = ProjectMember
        fields = [
            "id",
            "user_id",
            "display_name",
            "avatar_url",
            "role",
            "status",
            "weekly_capacity",
            "github_username",
            "github_user_id",
            "is_github_verified",
            "joined_at",
            "left_at",
            "updated_at",
        ]
