from rest_framework import serializers

from apps.groups.models import GroupJoinRequest
from apps.groups.serializers.validators import MinimalProfileSerializer
from common.serializers import StrictInputSerializer

JOIN_REQUEST_STATUS_CHOICES = ("PENDING", "APPROVED", "REJECTED", "CANCELLED")


class GroupJoinRequestSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=JOIN_REQUEST_STATUS_CHOICES, read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    requester_profile = MinimalProfileSerializer(read_only=True, allow_null=True, required=False)

    class Meta:
        model = GroupJoinRequest
        fields = [
            "id",
            "class_section_id",
            "group_id",
            "group_name",
            "enrollment_id",
            "user_id",
            "requester_profile",
            "status",
            "message",
            "review_note",
            "reviewed_by_user_id",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]


class JoinRequestCreateSerializer(StrictInputSerializer):
    message = serializers.CharField(
        max_length=500, allow_blank=True, trim_whitespace=True, required=False, default=""
    )


class JoinRequestReviewSerializer(StrictInputSerializer):
    review_note = serializers.CharField(
        max_length=500, allow_blank=True, trim_whitespace=True, required=False, default=""
    )


class JoinRequestCancelSerializer(StrictInputSerializer):
    pass
