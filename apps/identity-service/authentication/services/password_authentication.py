"""Authentication backend adaptation for the Identity user model."""

from accounts.models import AccountStatus
from common.errors import IdentityAPIError


class PasswordAuthenticationService:
    """Account lifecycle policy after Django/allauth validates login credentials."""

    @staticmethod
    def validate_login_account(user):
        if user.account_status == AccountStatus.SUSPENDED:
            raise IdentityAPIError("ACCOUNT_SUSPENDED", "Account suspended.", status_code=403)
        if not user.is_active:
            raise IdentityAPIError(
                "ACCOUNT_PENDING_ACTIVATION", "Account unavailable.", status_code=403
            )
