from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from accounts.models import AccountStatus, GlobalRoleCode, UserProfile
from common.errors import IdentityAPIError
from common.serializers import StrictInputMixin


class ProfilePatchSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = (
            "first_name",
            "last_name",
            "phone_number",
            "bio",
            "academic_year",
            "faculty",
            "timezone",
            "preferences",
        )

    def to_internal_value(self, data):
        if "student_id" in data:
            raise IdentityAPIError(
                "STUDENT_ID_IMMUTABLE", "Không được tự sửa MSSV.", status_code=403
            )
        return super().to_internal_value(data)

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected a JSON object.")
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Unknown timezone.") from exc
        return value


class BatchUsersSerializer(StrictInputMixin, serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100)


class StatusChangeSerializer(StrictInputMixin, serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(AccountStatus.ACTIVE, AccountStatus.SUSPENDED), required=False
    )
    restore_deleted = serializers.BooleanField(required=False)
    reason = serializers.CharField(max_length=1000)

    def validate(self, attrs):
        if ("status" in attrs) == ("restore_deleted" in attrs) or attrs.get(
            "restore_deleted"
        ) is False:
            raise serializers.ValidationError("Provide status or restore_deleted=true exclusively.")
        return attrs


class RoleChangeSerializer(StrictInputMixin, serializers.Serializer):
    role_code = serializers.ChoiceField(choices=GlobalRoleCode.values)


class AdminQuerySerializer(StrictInputMixin, serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)
    role = serializers.ChoiceField(choices=GlobalRoleCode.values, required=False)
    status = serializers.ChoiceField(choices=AccountStatus.values, required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
