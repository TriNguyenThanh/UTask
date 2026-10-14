from rest_framework import serializers

from apps.collaboration.models import Attachment
from common.serializers import StrictInputSerializer


class AttachmentSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True, allow_null=True)
    task_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Attachment
        fields = [
            "id",
            "project_id",
            "task_id",
            "file_name",
            "file_size",
            "content_type",
            "status",
            "expires_at",
            "confirmed_at",
            "deleted_at",
            "uploaded_by_user_id",
            "created_at",
        ]


class PresignInputSerializer(StrictInputSerializer):
    file_name = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField(min_value=1, max_value=26214400)
    content_type = serializers.ChoiceField(
        choices=[
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
            "application/zip",
            "text/plain",
            "application/json",
        ]
    )

    def validate_file_name(self, value):
        name = value.replace("\\", "/").rsplit("/", 1)[-1]
        if name in {".", "..", ""} or any(ord(char) < 32 for char in name):
            raise serializers.ValidationError("Tên tệp tin không hợp lệ.")
        return name


class ConfirmAttachmentSerializer(StrictInputSerializer):
    attachment_id = serializers.UUIDField()


class PresignSerializer(serializers.Serializer):
    attachment_id = serializers.UUIDField()
    presigned_url = serializers.URLField()
    headers = serializers.DictField(child=serializers.CharField())
    expires_in = serializers.IntegerField()


class DownloadSerializer(serializers.Serializer):
    download_url = serializers.URLField()
    expires_in = serializers.IntegerField()
