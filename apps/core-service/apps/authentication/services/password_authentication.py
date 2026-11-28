"""Authentication backend adaptation for the Identity user model."""

from apps.accounts.models import AccountStatus
from common.errors import CoreAPIError


class PasswordAuthenticationService:
    """Account lifecycle policy after Django/allauth validates login credentials."""

    @staticmethod
    def validate_login_account(user):
        if user.account_status == AccountStatus.SUSPENDED:
            raise CoreAPIError(
                "ACCOUNT_SUSPENDED",
                "Tài khoản đã bị đình chỉ. Vui lòng liên hệ người quản trị.",
                status_code=403,
            )
        if not user.is_active:
            raise CoreAPIError(
                "ACCOUNT_PENDING_ACTIVATION", "Tài khoản chưa được kích hoạt.", status_code=403
            )
