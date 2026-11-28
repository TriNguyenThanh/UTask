from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import AuditLog
from apps.accounts.serializers.commands import (
    AdminAuditLogQuerySerializer,
    AdminCreateUserSerializer,
    AdminQuerySerializer,
    AdminSessionsQuerySerializer,
    AdminUserPatchSerializer,
    EmptyCommandSerializer,
    RoleChangeSerializer,
    StatusChangeSerializer,
)
from apps.accounts.serializers.profiles import (
    AdminAuditLogSerializer,
    AdminSessionSerializer,
    AdminUserDetailSerializer,
    AdminUserSerializer,
)
from apps.accounts.services.administration import (
    admin_list_sessions,
    admin_revoke_all_sessions,
    admin_revoke_session,
    change_role,
    change_status,
    create_admin_user,
    soft_delete_user,
    unlock_login,
    update_admin_user,
)
from apps.accounts.services.profiles import admin_users
from common.errors import CoreAPIError
from common.pagination import StandardPagePagination
from common.permissions import SystemAdminPermission
from config.api_documentation import RoleChangeAutoSchema


@extend_schema_view(
    get=extend_schema(parameters=[AdminQuerySerializer], responses=AdminUserSerializer(many=True)),
    post=extend_schema(
        request=AdminCreateUserSerializer,
        responses={201: AdminUserDetailSerializer},
    ),
)
class AdminUsersView(ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    pagination_class = StandardPagePagination
    success_messages = {
        "GET": "Lấy danh sách người dùng thành công.",
        "POST": "Tạo tài khoản người dùng thành công.",
    }

    def get_queryset(self):
        query = AdminQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        users = admin_users(params.get("deleted", "active"))
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
        return users.distinct().order_by("-created_at", "pk")

    def post(self, request):
        serializer = AdminCreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_admin_user(request, serializer.validated_data)
        return Response(
            AdminUserDetailSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(responses=AdminUserDetailSerializer),
    patch=extend_schema(
        request=AdminUserPatchSerializer,
        responses=AdminUserDetailSerializer,
    ),
    delete=extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "AdminSoftDeleteData",
                fields={
                    "user_id": serializers.UUIDField(),
                    "account_status": serializers.CharField(),
                    "deleted_at": serializers.DateTimeField(allow_null=True),
                },
            )
        },
    ),
)
class AdminUserDetailView(GenericAPIView):
    serializer_class = AdminUserDetailSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    http_method_names = ["get", "patch", "delete", "head", "options"]
    success_messages = {
        "GET": "Lấy thông tin chi tiết người dùng thành công.",
        "PATCH": "Cập nhật thông tin người dùng thành công.",
        "DELETE": "Đã xóa mềm tài khoản người dùng.",
    }

    def get(self, request, user_id):
        user = admin_users("all").filter(pk=user_id).first()
        if user is None:
            raise CoreAPIError("RESOURCE_NOT_FOUND", "Không tìm thấy tài khoản.", status_code=404)
        return Response(AdminUserDetailSerializer(user).data)

    def patch(self, request, user_id):
        serializer = AdminUserPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_admin_user(request, user_id, serializer.validated_data)
        return Response(AdminUserDetailSerializer(user).data)

    def delete(self, request, user_id):
        return Response(soft_delete_user(request, user_id))


@extend_schema_view(
    post=extend_schema(
        request=EmptyCommandSerializer,
        responses=inline_serializer(
            "UnlockLoginData",
            fields={
                "user_id": serializers.UUIDField(),
                "is_login_locked": serializers.BooleanField(),
                "cleared_attempts": serializers.IntegerField(),
            },
        ),
    )
)
class AdminUnlockLoginView(GenericAPIView):
    serializer_class = EmptyCommandSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    success_message = "Đã mở khóa đăng nhập cho tài khoản."

    def post(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(unlock_login(request, user_id))


@extend_schema_view(get=extend_schema(parameters=[AdminAuditLogQuerySerializer]))
class AdminAuditLogsView(ListAPIView):
    serializer_class = AdminAuditLogSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    pagination_class = StandardPagePagination
    success_message = "Lấy nhật ký kiểm toán thành công."

    def get_queryset(self):
        query = AdminAuditLogQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        logs = AuditLog.objects.all()
        if params.get("actor_id"):
            logs = logs.filter(actor_id=params["actor_id"])
        if params.get("target_user_id"):
            logs = logs.filter(target_user_id=params["target_user_id"])
        if params.get("action"):
            logs = logs.filter(action=params["action"])
        if params.get("created_from"):
            logs = logs.filter(created_at__gte=params["created_from"])
        if params.get("created_to"):
            logs = logs.filter(created_at__lte=params["created_to"])
        return logs.order_by("-created_at", "-id")


@extend_schema_view(get=extend_schema(parameters=[AdminSessionsQuerySerializer]))
class AdminUserSessionsView(ListAPIView):
    serializer_class = AdminSessionSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    pagination_class = None
    success_message = "Lấy danh sách phiên đăng nhập của người dùng thành công."

    def get_queryset(self):
        query = AdminSessionsQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return admin_list_sessions(
            self.kwargs["user_id"],
            include_revoked=query.validated_data["include_revoked"],
        )


@extend_schema_view(
    delete=extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "AdminRevokeSessionData",
                fields={
                    "user_id": serializers.UUIDField(),
                    "session_id": serializers.UUIDField(),
                    "revoked": serializers.BooleanField(),
                },
            )
        },
    )
)
class AdminUserSessionRevokeView(GenericAPIView):
    serializer_class = AdminSessionSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    http_method_names = ["delete", "options"]
    success_message = "Đã thu hồi phiên đăng nhập của người dùng."

    def delete(self, request, user_id, session_id):
        return Response(admin_revoke_session(request, user_id, session_id))


@extend_schema_view(
    post=extend_schema(
        request=EmptyCommandSerializer,
        responses=inline_serializer(
            "AdminRevokeAllSessionsData",
            fields={
                "user_id": serializers.UUIDField(),
                "revoked_sessions_count": serializers.IntegerField(),
            },
        ),
    )
)
class AdminUserSessionsRevokeAllView(GenericAPIView):
    serializer_class = EmptyCommandSerializer
    permission_classes = [IsAuthenticated, SystemAdminPermission]
    success_message = "Đã thu hồi toàn bộ phiên đăng nhập của người dùng."

    def post(self, request, user_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(admin_revoke_all_sessions(request, user_id))


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
        request=RoleChangeSerializer,
        responses=inline_serializer(
            "AssignedRoles",
            fields={
                "user_id": serializers.UUIDField(),
                "roles": serializers.ListField(child=serializers.CharField()),
            },
        ),
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
    schema = RoleChangeAutoSchema()
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
