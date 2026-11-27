from dj_rest_auth.serializers import UserDetailsSerializer
from django.utils import timezone
from rest_framework import serializers

from accounts.models import AuditLog, GlobalRoleCode, User, UserSession


class _UserSummarySerializer(UserDetailsSerializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    username = serializers.CharField(read_only=True)
    student_id = serializers.CharField(read_only=True, allow_null=True)
    display_name = serializers.CharField(source="profile.display_name", read_only=True)
    avatar_url = serializers.CharField(source="profile.avatar_url", read_only=True, allow_null=True)
    roles = serializers.SerializerMethodField()

    class Meta(UserDetailsSerializer.Meta):
        model = User
        fields = ("id", "email", "username", "student_id", "display_name", "avatar_url", "roles")
        read_only_fields = fields

    @staticmethod
    def get_roles(user: User) -> list[str]:
        return sorted(assignment.role.code for assignment in user.global_role_assignments.all())


class PublicUserSerializer(_UserSummarySerializer):
    account_status = serializers.CharField(read_only=True)
    bio = serializers.CharField(source="profile.bio", read_only=True, allow_null=True)

    class Meta(_UserSummarySerializer.Meta):
        fields = (
            "id",
            "email",
            "student_id",
            "display_name",
            "avatar_url",
            "bio",
            "roles",
            "account_status",
        )
        read_only_fields = fields


class UserSearchSerializer(_UserSummarySerializer):
    class Meta(_UserSummarySerializer.Meta):
        fields = (
            "id",
            "display_name",
            "email",
            "student_id",
            "avatar_url",
            "roles",
        )
        read_only_fields = fields


class UserSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        min_length=2,
        max_length=100,
        error_messages={
            "required": "Vui lòng nhập từ khóa tìm kiếm.",
            "blank": "Từ khóa tìm kiếm không được để trống.",
            "min_length": "Từ khóa tìm kiếm phải có ít nhất 2 ký tự.",
            "max_length": "Từ khóa tìm kiếm không được vượt quá 100 ký tự.",
        },
    )
    role = serializers.ChoiceField(
        choices=GlobalRoleCode.choices,
        required=False,
        error_messages={"invalid_choice": "Vai trò lọc không hợp lệ."},
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=20,
        default=10,
        required=False,
        error_messages={
            "invalid": "Giới hạn số lượng kết quả phải là số nguyên hợp lệ.",
            "min_value": "Giới hạn số lượng kết quả phải từ 1 đến 20.",
            "max_value": "Giới hạn số lượng kết quả phải từ 1 đến 20.",
        },
    )


class AdminUserSerializer(_UserSummarySerializer):
    is_email_verified = serializers.BooleanField(read_only=True)
    last_login_at = serializers.DateTimeField(source="last_login", read_only=True, allow_null=True)
    deleted_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta(_UserSummarySerializer.Meta):
        fields = (
            "id",
            "email",
            "username",
            "student_id",
            "display_name",
            "account_status",
            "is_email_verified",
            "roles",
            "last_login_at",
            "created_at",
            "deleted_at",
        )
        read_only_fields = fields


class AdminUserDetailSerializer(AdminUserSerializer):
    first_name = serializers.CharField(source="profile.first_name", read_only=True)
    last_name = serializers.CharField(source="profile.last_name", read_only=True)
    phone_number = serializers.CharField(
        source="profile.phone_number", read_only=True, allow_null=True
    )
    bio = serializers.CharField(source="profile.bio", read_only=True, allow_null=True)
    github_username = serializers.CharField(
        source="profile.github_username", read_only=True, allow_null=True
    )
    academic_year = serializers.CharField(
        source="profile.academic_year", read_only=True, allow_null=True
    )
    faculty = serializers.CharField(source="profile.faculty", read_only=True, allow_null=True)
    timezone = serializers.CharField(source="profile.timezone", read_only=True)
    has_usable_password = serializers.SerializerMethodField()
    linked_providers = serializers.SerializerMethodField()
    is_login_locked = serializers.SerializerMethodField()
    failed_login_attempts = serializers.SerializerMethodField()
    locked_until = serializers.SerializerMethodField()
    active_sessions_count = serializers.SerializerMethodField()

    class Meta(AdminUserSerializer.Meta):
        fields = AdminUserSerializer.Meta.fields + (
            "avatar_url",
            "first_name",
            "last_name",
            "phone_number",
            "bio",
            "github_username",
            "academic_year",
            "faculty",
            "timezone",
            "has_usable_password",
            "linked_providers",
            "is_login_locked",
            "failed_login_attempts",
            "locked_until",
            "active_sessions_count",
        )
        read_only_fields = fields

    def _lockout(self, user: User) -> dict:
        cache = self.context.setdefault("_lockout_cache", {})
        if user.pk not in cache:
            from accounts.services.administration import login_lockout_state

            cache[user.pk] = login_lockout_state(user)
        return cache[user.pk]

    @staticmethod
    def get_has_usable_password(user: User) -> bool:
        return user.has_usable_password()

    @staticmethod
    def get_linked_providers(user: User) -> list[str]:
        return sorted({account.provider for account in user.socialaccount_set.all()})

    def get_is_login_locked(self, user: User) -> bool:
        return self._lockout(user)["is_login_locked"]

    def get_failed_login_attempts(self, user: User) -> int:
        return self._lockout(user)["failed_login_attempts"]

    def get_locked_until(self, user: User) -> str | None:
        return self._lockout(user)["locked_until"]

    @staticmethod
    def get_active_sessions_count(user: User) -> int:
        return UserSession.objects.filter(
            user=user, is_revoked=False, expires_at__gt=timezone.now()
        ).count()


class AdminAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor_id",
            "action",
            "target_user_id",
            "ip_address",
            "user_agent",
            "details",
            "created_at",
        )
        read_only_fields = fields


class AdminSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = (
            "id",
            "token_family",
            "device_name",
            "ip_address",
            "user_agent",
            "is_revoked",
            "revoked_at",
            "revoked_reason",
            "created_at",
            "expires_at",
        )
        read_only_fields = fields


class CurrentUserSerializer(_UserSummarySerializer):
    first_name = serializers.CharField(source="profile.first_name", read_only=True)
    last_name = serializers.CharField(source="profile.last_name", read_only=True)
    phone_number = serializers.CharField(
        source="profile.phone_number", read_only=True, allow_null=True
    )
    bio = serializers.CharField(source="profile.bio", read_only=True, allow_null=True)
    github_username = serializers.CharField(
        source="profile.github_username", read_only=True, allow_null=True
    )
    academic_year = serializers.CharField(
        source="profile.academic_year", read_only=True, allow_null=True
    )
    faculty = serializers.CharField(source="profile.faculty", read_only=True, allow_null=True)
    timezone = serializers.CharField(source="profile.timezone", read_only=True)
    preferences = serializers.JSONField(source="profile.preferences", read_only=True)
    has_usable_password = serializers.SerializerMethodField()
    linked_providers = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    class Meta(_UserSummarySerializer.Meta):
        fields = _UserSummarySerializer.Meta.fields + (
            "first_name",
            "last_name",
            "phone_number",
            "bio",
            "github_username",
            "academic_year",
            "faculty",
            "timezone",
            "preferences",
            "has_usable_password",
            "linked_providers",
            "created_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_has_usable_password(user: User) -> bool:
        return user.has_usable_password()

    @staticmethod
    def get_linked_providers(user: User) -> list[str]:
        return sorted({account.provider for account in user.socialaccount_set.all()})
