from rest_framework import serializers

from apps.groups.models import GroupMember
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
            "joined_at",
            "left_at",
            "profile",
        ]


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
