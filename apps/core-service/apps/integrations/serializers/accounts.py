from rest_framework import serializers

from common.serializers import StrictInputSerializer


class UsernameInputSerializer(StrictInputSerializer):
    github_username = serializers.CharField(
        max_length=100,
        error_messages={"blank": "Vui lòng nhập tên tài khoản GitHub của bạn."},
    )


class MappingSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    github_username = serializers.CharField(allow_null=True)
    is_github_verified = serializers.BooleanField()


class RequestedSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    user_id = serializers.UUIDField()
    requested_by_user_id = serializers.UUIDField()
