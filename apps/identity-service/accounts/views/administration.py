from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import SystemAdminPermission
from accounts.serializers.commands import (
    AdminQuerySerializer,
    RoleChangeSerializer,
    StatusChangeSerializer,
)
from accounts.serializers.profiles import AdminUserSerializer
from accounts.services.administration import change_role, change_status
from accounts.services.profiles import public_users
from common.pagination import IdentityPagePagination


@extend_schema_view(get=extend_schema(parameters=[AdminQuerySerializer]))
class AdminUsersView(ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    pagination_class = IdentityPagePagination
    success_message = "Lấy danh sách người dùng thành công."

    def get_queryset(self):
        query = AdminQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        users = public_users()
        if params.get("search"):
            term = params["search"]
            users = users.filter(
                Q(email__icontains=term)
                | Q(username__icontains=term)
                | Q(student_id__icontains=term)
                | Q(profile__display_name__icontains=term)
            )
        if params.get("role"):
            users = users.filter(global_role_assignments__role__code=params["role"])
        if params.get("status"):
            users = users.filter(account_status=params["status"])
        return users.order_by("-created_at", "pk")


@extend_schema_view(
    patch=extend_schema(
        responses=inline_serializer(
            "StatusData",
            fields={
                "user_id": serializers.UUIDField(),
                "account_status": serializers.CharField(),
                "deleted_at": serializers.DateTimeField(allow_null=True),
            },
        )
    )
)
class AdminStatusView(GenericAPIView):
    serializer_class = StatusChangeSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    success_message = "Cập nhật trạng thái tài khoản người dùng thành công."

    def patch(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(change_status(request, user_id, serializer.validated_data))


@extend_schema_view(
    post=extend_schema(
        responses=inline_serializer(
            "AssignedRoles",
            fields={
                "user_id": serializers.UUIDField(),
                "roles": serializers.ListField(child=serializers.CharField()),
            },
        )
    ),
    delete=extend_schema(
        request=RoleChangeSerializer,
        responses={
            200: inline_serializer(
                "RevokedRoles",
                fields={
                    "user_id": serializers.UUIDField(),
                    "roles": serializers.ListField(child=serializers.CharField()),
                },
            )
        },
    ),
)
class AdminRoleView(GenericAPIView):
    serializer_class = RoleChangeSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    success_messages = {
        "POST": "Gán vai trò toàn cục thành công.",
        "DELETE": "Thu hồi vai trò toàn cục thành công.",
    }

    def post(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            change_role(request, user_id, serializer.validated_data["role_code"], assign=True)
        )

    def delete(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            change_role(request, user_id, serializer.validated_data["role_code"], assign=False)
        )
