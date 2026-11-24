from dj_rest_auth.views import UserDetailsView
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import GlobalRoleCode
from accounts.permissions import ClassroomActorPermission
from accounts.serializers.commands import BatchUsersSerializer, ProfilePatchSerializer
from accounts.serializers.profiles import (
    CurrentUserSerializer,
    PublicUserSerializer,
    UserSearchQuerySerializer,
    UserSearchSerializer,
)
from accounts.services.profiles import public_users, search_active_users, update_profile


@extend_schema_view(
    patch=extend_schema(
        request=ProfilePatchSerializer,
        responses=CurrentUserSerializer,
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
        user = public_users().get(pk=profile.user_id)
        return Response(CurrentUserSerializer(user).data)


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


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "q",
                str,
                required=True,
                description=(
                    "Từ khóa tìm kiếm (tối thiểu 2 ký tự) theo email, tên đăng nhập, "
                    "MSSV hoặc tên hiển thị."
                ),
            ),
            OpenApiParameter(
                "role",
                str,
                required=False,
                enum=list(GlobalRoleCode.values),
                description="Lọc theo vai trò toàn cục (TEACHER, STUDENT, SYSTEM_ADMIN).",
            ),
            OpenApiParameter(
                "limit",
                int,
                required=False,
                description="Số kết quả tối đa (mặc định 10, tối đa 20).",
            ),
        ],
        responses=inline_serializer(
            "UserSearchResults",
            fields={"users": UserSearchSerializer(many=True)},
        ),
    )
)
class UserSearchView(GenericAPIView):
    permission_classes = [IsAuthenticated, ClassroomActorPermission]
    serializer_class = UserSearchSerializer
    throttle_scope = "user_search"
    success_message = "Tìm kiếm người dùng thành công."

    def get(self, request):
        query_serializer = UserSearchQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        q = query_serializer.validated_data["q"]
        role = query_serializer.validated_data.get("role")
        limit = query_serializer.validated_data.get("limit", 10)
        rows = search_active_users(q, role=role, limit=limit)
        data = UserSearchSerializer(rows, many=True).data
        response = Response({"users": data})
        response.identity_meta = {"total": len(data), "limit": limit}
        return response
