from dj_rest_auth.serializers import UserDetailsSerializer
from rest_framework import serializers

from accounts.models import User


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
    bio = serializers.CharField(source="profile.bio", read_only=True, allow_null=True)

    class Meta(_UserSummarySerializer.Meta):
        fields = ("id", "email", "student_id", "display_name", "avatar_url", "bio", "roles")
        read_only_fields = fields


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
