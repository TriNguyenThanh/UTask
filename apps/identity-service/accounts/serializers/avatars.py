from rest_framework import serializers

from common.errors import IdentityAPIError
from common.serializers import StrictInputMixin

IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024


class AvatarPresignSerializer(StrictInputMixin, serializers.Serializer):
    file_name = serializers.CharField(max_length=255)
    content_type = serializers.CharField()
    file_size = serializers.IntegerField(min_value=1)

    def validate_content_type(self, value):
        if value not in IMAGE_EXTENSIONS:
            raise IdentityAPIError("INVALID_IMAGE_TYPE", "Chỉ hỗ trợ JPEG, PNG hoặc WebP.")
        return value

    def validate_file_size(self, value):
        if value > MAX_AVATAR_SIZE:
            raise IdentityAPIError("FILE_SIZE_EXCEEDS_LIMIT", "Ảnh không được vượt 5 MB.")
        return value


class AvatarConfirmSerializer(StrictInputMixin, serializers.Serializer):
    file_key = serializers.CharField(max_length=255)
