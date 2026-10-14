from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.collaboration.serializers import CommentSerializer


class MentionIntentSerializer(serializers.Serializer):
    comment_id = serializers.UUIDField()
    task_id = serializers.UUIDField(allow_null=True)
    recipient_ids = serializers.ListField(child=serializers.UUIDField())
    actor_user_id = serializers.UUIDField()


class TeacherFeedbackEventSerializer(CommentSerializer):
    scope_source_version = serializers.SerializerMethodField()
    recipient_ids = serializers.SerializerMethodField()

    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + ["scope_source_version", "recipient_ids"]

    @extend_schema_field(serializers.IntegerField(min_value=0))
    def get_scope_source_version(self, comment):
        return self.context["scope_source_version"]

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_recipient_ids(self, comment):
        return [str(value) for value in self.context["recipient_ids"]]


class AttachmentExpiredEventSerializer(serializers.Serializer):
    attachment_id = serializers.UUIDField()
