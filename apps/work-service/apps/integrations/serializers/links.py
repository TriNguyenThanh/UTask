from rest_framework import serializers

from apps.integrations.models import TaskGitHubLink
from common.serializers import StrictInputSerializer


class GitHubLinkSerializer(serializers.ModelSerializer):
    task_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = TaskGitHubLink
        fields = [
            "id",
            "task_id",
            "github_repo_id",
            "connection_generation",
            "source_version",
            "confirmation_status",
            "confirmed_by_user_id",
            "confirmed_at",
            "deleted_at",
            "link_type",
            "github_ref_id",
            "github_title",
            "github_status",
            "github_url",
            "is_verified",
            "created_by_user_id",
            "synced_at",
        ]


class LinkInputSerializer(StrictInputSerializer):
    link_type = serializers.ChoiceField(choices=TaskGitHubLink.Type.choices)
    github_ref_id = serializers.CharField(max_length=300)

    def validate(self, attrs):
        if attrs["link_type"] == "PULL_REQUEST":
            ref = attrs["github_ref_id"].removeprefix("#")
            if not ref.isascii() or not ref.isdecimal() or int(ref) < 1:
                raise serializers.ValidationError(
                    {"github_ref_id": "Mã yêu cầu kéo (Pull Request) phải là số nguyên dương."}
                )
            attrs["github_ref_id"] = str(int(ref))
        return attrs


class UnlinkedSerializer(StrictInputSerializer):
    unlinked_id = serializers.UUIDField()
