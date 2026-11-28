from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.collaboration.models import Comment
from common.serializers import StrictInputSerializer


class CommentSerializer(serializers.ModelSerializer):
    task_id = serializers.UUIDField(read_only=True, allow_null=True)
    project_id = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True, default="")
    avatar_url = serializers.CharField(read_only=True, default=None, allow_null=True)
    mentioned_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "project_id",
            "task_id",
            "user_id",
            "display_name",
            "avatar_url",
            "content_html",
            "content_stripped",
            "is_teacher_feedback",
            "created_at",
            "updated_at",
            "deleted_at",
            "mentioned_user_ids",
        ]

    @extend_schema_field(serializers.UUIDField())
    def get_project_id(self, comment):
        return str(comment.project_id or comment.task.project_id)

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_mentioned_user_ids(self, comment):
        return [str(row.user_id) for row in comment.mentions.all()]


class CommentInputSerializer(StrictInputSerializer):
    task_id = serializers.UUIDField(required=False)
    project_id = serializers.UUIDField(required=False)
    content_html = serializers.CharField(max_length=100000)
    mentioned_user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách người được nhắc tên không được vượt quá 100 mục."},
    )

    def validate(self, data):
        if ("task_id" in data) == ("project_id" in data):
            raise serializers.ValidationError(
                "Bình luận phải gắn với chính xác một công việc hoặc dự án."
            )
        return data


class EditCommentSerializer(StrictInputSerializer):
    content_html = serializers.CharField(max_length=100000)
    mentioned_user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách người được nhắc tên không được vượt quá 100 mục."},
    )
