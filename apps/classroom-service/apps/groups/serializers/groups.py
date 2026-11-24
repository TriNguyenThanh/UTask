from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.groups.models import GroupProjectLink, StudyGroup
from apps.groups.serializers.members import MemberSerializer
from common.serializers import StrictInputSerializer


class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    leader_id = serializers.SerializerMethodField()

    class Meta:
        model = StudyGroup
        exclude = ["invite_code_hash"]

    @extend_schema_field(serializers.IntegerField(min_value=0))
    def get_member_count(self, obj):
        if hasattr(obj, "_member_count"):
            return obj._member_count
        return obj.members.filter(status="ACTIVE").count()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_leader_id(self, obj):
        if hasattr(obj, "_leader_id"):
            value = obj._leader_id
            return str(value) if value is not None else None
        leader = (
            obj.members.filter(status="ACTIVE", role="LEADER")
            .values_list("enrollment__user_id", flat=True)
            .first()
        )
        return str(leader) if leader is not None else None


class MyGroupSerializer(GroupSerializer):
    my_role = serializers.ChoiceField(choices=["LEADER", "MEMBER"], read_only=True)
    members = MemberSerializer(source="_active_members", many=True, read_only=True)


class GroupCreateSerializer(StrictInputSerializer):
    class_id = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    leader_id = serializers.UUIDField(required=False)


class GroupPatchSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False)
    status = serializers.ChoiceField(choices=["ACTIVE", "ARCHIVED"], required=False)
    reason = serializers.CharField(min_length=1, max_length=500, required=False)

    def validate(self, attrs):
        if attrs.get("status") == "ARCHIVED" and not str(attrs.get("reason") or "").strip():
            raise serializers.ValidationError({"reason": "Cần nêu lý do khi lưu trữ nhóm học tập."})
        return attrs


class ProjectLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupProjectLink
        fields = ["id", "class_section_id", "group_id", "project_id", "linked_at"]
