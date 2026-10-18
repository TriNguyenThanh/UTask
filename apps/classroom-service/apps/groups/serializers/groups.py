from rest_framework import serializers

from apps.groups.models import GroupProjectLink, StudyGroup
from common.serializers import StrictInputSerializer


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyGroup
        exclude = ["invite_code_hash"]


class GroupCreateSerializer(StrictInputSerializer):
    class_id = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    leader_id = serializers.UUIDField(required=False)


class GroupPatchSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False)
    status = serializers.ChoiceField(choices=["ACTIVE", "ARCHIVED"], required=False)


class ProjectLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupProjectLink
        fields = ["id", "class_section_id", "group_id", "project_id", "linked_at"]
