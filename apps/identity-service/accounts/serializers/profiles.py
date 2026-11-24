from dj_rest_auth.serializers import UserDetailsSerializer
from rest_framework import serializers

from accounts.models import GlobalRoleCode, User


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
            "created_at",
        )
        read_only_fields = fields
