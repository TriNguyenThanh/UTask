from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import AccountStatus, GlobalRoleCode, User, UserProfile
from apps.accounts.serializers.mixins import StrictInputMixin


class ProfilePatchSerializer(StrictInputMixin, serializers.ModelSerializer):
    student_id = serializers.CharField(
        max_length=50, required=False, allow_null=True, allow_blank=True
    )

    class Meta:
        model = UserProfile
        fields = (
            "student_id",
            "first_name",
            "last_name",
            "phone_number",
            "bio",
            "academic_year",
            "faculty",
            "timezone",
            "preferences",
        )

    def validate_student_id(self, value):
        return User.objects.normalize_student_id(value)

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Cần gửi thông tin tùy chọn dưới dạng một đối tượng JSON."
            )
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Múi giờ không hợp lệ.") from exc
        return value


class BatchUsersSerializer(StrictInputMixin, serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100)


class StatusChangeSerializer(StrictInputMixin, serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(AccountStatus.ACTIVE, AccountStatus.SUSPENDED), required=False
    )
    restore_deleted = serializers.BooleanField(required=False)
    reset_lockout = serializers.BooleanField(required=False)
    reason = serializers.CharField(max_length=1000)

    def validate(self, attrs):
        if ("status" in attrs) == ("restore_deleted" in attrs) or attrs.get(
            "restore_deleted"
        ) is False:
            raise serializers.ValidationError(
                "Chỉ chọn đổi trạng thái hoặc khôi phục tài khoản đã xóa."
            )
        if attrs.get("reset_lockout") and attrs.get("status") == AccountStatus.SUSPENDED:
            raise serializers.ValidationError(
                "Không thể đồng thời đình chỉ tài khoản và mở khóa đăng nhập."
            )
        return attrs


class RoleChangeSerializer(StrictInputMixin, serializers.Serializer):
    role_code = serializers.ChoiceField(choices=GlobalRoleCode.choices)


class AdminQuerySerializer(StrictInputMixin, serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)
    role = serializers.ChoiceField(choices=GlobalRoleCode.choices, required=False)
    status = serializers.ChoiceField(choices=AccountStatus.values, required=False)
    deleted = serializers.ChoiceField(
        choices=("active", "deleted", "all"), required=False, default="active"
    )
    page = serializers.IntegerField(min_value=1, default=1)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)


class AdminCreateUserSerializer(StrictInputMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    username = serializers.CharField(
        max_length=100, required=False, allow_blank=True, allow_null=True
    )
    first_name = serializers.CharField(max_length=100, required=False, default="", allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, default="", allow_blank=True)
    student_id = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True
    )
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=GlobalRoleCode.choices),
        min_length=1,
        max_length=len(GlobalRoleCode.values),
        required=False,
        default=[GlobalRoleCode.STUDENT],
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=False, max_length=128
    )
    send_activation_email = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        return User.objects.normalize_email(value)

    def validate_username(self, value):
        return User.objects.normalize_username(value)

    def validate_student_id(self, value):
        return User.objects.normalize_student_id(value)

    def validate_roles(self, value):
        return list(dict.fromkeys(value))

    def validate(self, attrs):
        send_mail = attrs.get("send_activation_email", False)
        password = attrs.get("password")
        if send_mail and password:
            raise serializers.ValidationError(
                "Không gửi mật khẩu ban đầu khi chọn gửi email kích hoạt."
            )
        if not send_mail and not password:
            raise serializers.ValidationError(
                "Cần nhập mật khẩu ban đầu hoặc bật gửi email kích hoạt."
            )
        if password:
            candidate = User(
                email=attrs["email"],
                username=attrs.get("username") or attrs["email"].partition("@")[0],
            )
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class AdminUserPatchSerializer(ProfilePatchSerializer):
    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Cần cung cấp ít nhất một trường để cập nhật.")
        return attrs


class AdminAuditLogQuerySerializer(StrictInputMixin, serializers.Serializer):
    actor_id = serializers.CharField(required=False, max_length=100)
    target_user_id = serializers.CharField(required=False, max_length=100)
    action = serializers.CharField(required=False, max_length=60)
    created_from = serializers.DateTimeField(required=False)
    created_to = serializers.DateTimeField(required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)

    def validate(self, attrs):
        start, end = attrs.get("created_from"), attrs.get("created_to")
        if start and end and start > end:
            raise serializers.ValidationError(
                "Thời điểm bắt đầu không được lớn hơn thời điểm kết thúc."
            )
        return attrs


class AdminSessionsQuerySerializer(StrictInputMixin, serializers.Serializer):
    include_revoked = serializers.BooleanField(required=False, default=False)


class EmptyCommandSerializer(StrictInputMixin, serializers.Serializer):
    pass


class SelfDeleteAccountSerializer(StrictInputMixin, serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=False, max_length=128
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class EmailChangeRequestSerializer(StrictInputMixin, serializers.Serializer):
    new_email = serializers.EmailField(max_length=255)
    current_password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=False, max_length=128
    )

    def validate_new_email(self, value):
        return User.objects.normalize_email(value)


class EmailChangeConfirmSerializer(StrictInputMixin, serializers.Serializer):
    token = serializers.CharField(min_length=16, max_length=255)
