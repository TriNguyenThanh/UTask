from rest_framework import serializers

from apps.messaging.models import Activity
from common.serializers import StrictInputSerializer

ACTIVITY_SUBJECT_TYPES = [
    "PROJECT",
    "PROJECT_MEMBER",
    "STATE",
    "TASK",
    "EPIC",
    "LABEL",
    "COMMENT",
    "SPRINT",
]


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ["id", "actor_user_id", "verb", "field", "old_value", "new_value", "created_at"]


class ProjectActivityFilterSerializer(StrictInputSerializer):
    subject_type = serializers.ChoiceField(choices=ACTIVITY_SUBJECT_TYPES, required=False)
    verb = serializers.CharField(required=False, max_length=100, allow_blank=False)
    actor_user_id = serializers.UUIDField(required=False)
    created_from = serializers.DateTimeField(required=False)
    created_to = serializers.DateTimeField(required=False)
    cursor = serializers.CharField(required=False, max_length=4096)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def validate(self, attrs):
        created_from = attrs.get("created_from")
        created_to = attrs.get("created_to")
        if created_from and created_to and created_from > created_to:
            raise serializers.ValidationError(
                {"created_to": "Thời điểm kết thúc không được diễn ra trước thời điểm bắt đầu."}
            )
        return attrs


class ProjectActivitySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    subject_type = serializers.ChoiceField(choices=ACTIVITY_SUBJECT_TYPES, read_only=True)
    subject_id = serializers.UUIDField(allow_null=True, read_only=True)
    actor_user_id = serializers.UUIDField(allow_null=True, read_only=True)
    actor_display_name = serializers.CharField(read_only=True)
    actor_avatar_url = serializers.CharField(allow_null=True, read_only=True)
    verb = serializers.CharField(read_only=True)
    field = serializers.CharField(allow_null=True, read_only=True)
    old_value = serializers.CharField(allow_null=True, read_only=True)
    new_value = serializers.CharField(allow_null=True, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
