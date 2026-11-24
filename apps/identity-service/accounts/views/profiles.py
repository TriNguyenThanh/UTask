from dj_rest_auth.jwt_auth import unset_jwt_cookies
from dj_rest_auth.views import UserDetailsView
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import GlobalRoleCode
from accounts.permissions import ClassroomActorPermission
from accounts.serializers.commands import (
    BatchUsersSerializer,
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    ProfilePatchSerializer,
    SelfDeleteAccountSerializer,
)
from accounts.serializers.profiles import (
    CurrentUserSerializer,
    PublicUserSerializer,
    UserSearchQuerySerializer,
    UserSearchSerializer,
)
from accounts.services.profiles import public_users, search_active_users, update_profile
from accounts.services.self_service import (
    confirm_email_change,
    request_email_change,
    self_delete_account,
)
from config.api_documentation import RoleChangeAutoSchema


@extend_schema_view(
    patch=extend_schema(
        request=ProfilePatchSerializer,
        responses=CurrentUserSerializer,
    ),
    delete=extend_schema(
        request=SelfDeleteAccountSerializer,
        responses={
            200: inline_serializer(
                "SelfDeleteAccountData",
                fields={
                    "user_id": serializers.UUIDField(),
                    "account_status": serializers.CharField(),
                    "deleted_at": serializers.DateTimeField(allow_null=True),
                },
            )
        },
    ),
)
class CurrentUserView(UserDetailsView):
    schema = RoleChangeAutoSchema()
    http_method_names = ["get", "patch", "delete", "head", "options"]
    success_messages = {
        "GET": "Lấy thông tin hồ sơ cá nhân thành công.",
        "PATCH": "Cập nhật hồ sơ cá nhân thành công.",
        "DELETE": "Đã vô hiệu hóa tài khoản của bạn.",
    }

    def get_object(self):
        return public_users().get(pk=self.request.user.pk)

    def patch(self, request, *args, **kwargs):
        serializer = ProfilePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = update_profile(request, serializer.validated_data)
        user = public_users().get(pk=profile.user_id)
        return Response(CurrentUserSerializer(user).data)

    def delete(self, request, *args, **kwargs):
        serializer = SelfDeleteAccountSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        result = self_delete_account(request, serializer.validated_data)
        response = Response(result)
        unset_jwt_cookies(response)
        return response


@extend_schema_view(
    post=extend_schema(
        request=EmailChangeRequestSerializer,
        responses=inline_serializer(
            "EmailChangeRequestData",
            fields={
                "new_email": serializers.EmailField(),
                "expires_in": serializers.IntegerField(),
            },
        ),
    )
)
class EmailChangeRequestView(GenericAPIView):
    serializer_class = EmailChangeRequestSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = "recovery"
    success_message = "Đã gửi hướng dẫn xác minh tới địa chỉ email mới."

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(request_email_change(request, serializer.validated_data))


@extend_schema_view(
    post=extend_schema(
        request=EmailChangeConfirmSerializer,
        responses=CurrentUserSerializer,
    )
)
class EmailChangeConfirmView(GenericAPIView):
    serializer_class = EmailChangeConfirmSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = "recovery"
    success_message = "Cập nhật địa chỉ email thành công."

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = confirm_email_change(request, serializer.validated_data["token"])
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
