from rest_framework import serializers

from apps.groups.models import GroupMember
from apps.groups.serializers.validators import SkillsListField
from common.serializers import StrictInputSerializer


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="enrollment.user_id")
    profile = serializers.DictField(read_only=True, required=False)

    class Meta:
        model = GroupMember
        fields = [
            "id",
            "group_id",
            "user_id",
            "enrollment_id",
            "role",
            "status",
            "skills",
            "responsibility",
            "joined_at",
            "left_at",
            "profile",
        ]


class MemberSelfPatchSerializer(StrictInputSerializer):
    skills = SkillsListField(required=False)
    responsibility = serializers.CharField(
        max_length=200, allow_blank=True, trim_whitespace=True, required=False
    )

    def validate(self, attrs):
        if "skills" not in attrs and "responsibility" not in attrs:
            raise serializers.ValidationError(
                "Cần cung cấp ít nhất một thông tin để cập nhật (kỹ năng hoặc vai trò đảm nhiệm)."
            )
        return attrs


class MemberResponsibilityPatchSerializer(StrictInputSerializer):
    responsibility = serializers.CharField(max_length=200, allow_blank=True, trim_whitespace=True)


class MemberCommandSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=1, max_length=500)


class MemberLeaveSerializer(MemberCommandSerializer):
    dissolve_if_sole_member = serializers.BooleanField(required=False)


class MemberTargetSerializer(MemberCommandSerializer):
    user_id = serializers.UUIDField()


class MemberRemoveSerializer(MemberTargetSerializer):
    dissolve_if_sole_member = serializers.BooleanField(required=False)


class TeacherAdjustmentSerializer(StrictInputSerializer):
    user_id = serializers.UUIDField()
    target_group_id = serializers.UUIDField(allow_null=True)
    successor_user_id = serializers.UUIDField(required=False)
    dissolve_if_sole_member = serializers.BooleanField(required=False)
    reason = serializers.CharField(min_length=1, max_length=500)


class AdjustmentResultSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    group_id = serializers.UUIDField(allow_null=True)
