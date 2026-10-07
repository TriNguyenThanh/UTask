from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.serializers.avatars import AvatarConfirmSerializer, AvatarPresignSerializer
from accounts.services.avatars import confirm_avatar, presign_avatar


@extend_schema_view(
    post=extend_schema(
        responses=inline_serializer(
            "AvatarPresignData",
            fields={
                "upload_url": serializers.URLField(),
                "public_url": serializers.URLField(),
                "file_key": serializers.CharField(),
                "expires_in": serializers.IntegerField(),
            },
        )
    )
)
class AvatarPresignView(GenericAPIView):
    serializer_class = AvatarPresignSerializer
    success_message = "Khởi tạo URL tải ảnh đại diện thành công."

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(presign_avatar(request, serializer.validated_data))


@extend_schema_view(
    post=extend_schema(
        responses=inline_serializer(
            "AvatarConfirmData",
            fields={
                "avatar_url": serializers.URLField(),
            },
        )
    )
)
class AvatarConfirmView(GenericAPIView):
    serializer_class = AvatarConfirmSerializer
    success_message = "Cập nhật ảnh đại diện thành công."

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(confirm_avatar(request, serializer.validated_data["file_key"]))
