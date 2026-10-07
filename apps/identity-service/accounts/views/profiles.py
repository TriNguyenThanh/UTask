from dj_rest_auth.views import UserDetailsView
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.response import Response

from accounts.serializers.commands import BatchUsersSerializer, ProfilePatchSerializer
from accounts.serializers.profiles import PublicUserSerializer
from accounts.services.profiles import public_users, update_profile


@extend_schema_view(
    patch=extend_schema(
        request=ProfilePatchSerializer,
        responses=inline_serializer(
            "ProfilePatchData",
            fields={
                "display_name": serializers.CharField(),
                "phone_number": serializers.CharField(allow_null=True),
                "bio": serializers.CharField(allow_null=True),
                "preferences": serializers.DictField(),
            },
        ),
    )
)
class CurrentUserView(UserDetailsView):
    http_method_names = ["get", "patch", "head", "options"]
    success_messages = {
        "GET": "Lấy thông tin hồ sơ cá nhân thành công.",
        "PATCH": "Cập nhật hồ sơ cá nhân thành công.",
    }

    def patch(self, request, *args, **kwargs):
        serializer = ProfilePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = update_profile(request, serializer.validated_data)
        return Response(
            {
                "display_name": profile.display_name,
                "phone_number": profile.phone_number,
                "bio": profile.bio,
                "preferences": profile.preferences,
            }
        )


class PublicUserView(RetrieveAPIView):
    serializer_class = PublicUserSerializer
    success_message = "Lấy thông tin người dùng thành công."

    def get_object(self):
        return get_object_or_404(public_users(), pk=self.kwargs["user_id"])


@extend_schema_view(
    post=extend_schema(
        responses=inline_serializer(
            "PublicUsers",
            fields={
                "users": PublicUserSerializer(many=True),
            },
        )
    )
)
class BatchUsersView(GenericAPIView):
    serializer_class = BatchUsersSerializer
    success_message = "Truy vấn danh sách người dùng thành công."

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(serializer.validated_data["user_ids"]))
        found = {user.pk: user for user in public_users().filter(pk__in=ids)}
        data = PublicUserSerializer([found[i] for i in ids if i in found], many=True).data
        response = Response({"users": data})
        response.identity_meta = {"total": len(data)}
        return response
