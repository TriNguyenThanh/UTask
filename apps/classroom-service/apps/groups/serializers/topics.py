from rest_framework import serializers

from apps.groups.models import GroupTopicProposal
from common.serializers import StrictInputSerializer

TOPIC_STATUS_CHOICES = (
    "DRAFT",
    "PENDING",
    "APPROVED",
    "REVISION_REQUESTED",
    "REJECTED",
)
TOPIC_REVIEW_DECISION_CHOICES = (
    "APPROVED",
    "REVISION_REQUESTED",
    "REJECTED",
)


class TopicProposalSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=TOPIC_STATUS_CHOICES, read_only=True)

    class Meta:
        model = GroupTopicProposal
        fields = [
            "id",
            "class_section_id",
            "group_id",
            "title",
            "summary",
            "objectives",
            "status",
            "teacher_feedback",
            "submitted_by_user_id",
            "submitted_at",
            "reviewed_by_user_id",
            "reviewed_at",
            "version",
            "created_at",
            "updated_at",
        ]


class TopicProposalUpsertSerializer(StrictInputSerializer):
    title = serializers.CharField(min_length=1, max_length=200, trim_whitespace=True)
    summary = serializers.CharField(min_length=1, max_length=5000, trim_whitespace=True)
    objectives = serializers.CharField(
        max_length=5000, allow_blank=True, trim_whitespace=True, required=False, default=""
    )
    version = serializers.IntegerField(min_value=1, required=False)


class TopicSubmitSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)


class TopicReviewSerializer(StrictInputSerializer):
    decision = serializers.ChoiceField(choices=TOPIC_REVIEW_DECISION_CHOICES)
    feedback = serializers.CharField(
        max_length=5000, allow_blank=True, trim_whitespace=True, required=False, default=""
    )
    version = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if attrs["decision"] in {"REVISION_REQUESTED", "REJECTED"} and not attrs["feedback"]:
            raise serializers.ValidationError(
                {"feedback": ("Vui lòng nhập nhận xét khi yêu cầu chỉnh sửa hoặc từ chối đề tài.")}
            )
        return attrs
