"""Identity authentication components grouped by responsibility."""

from allauth.account.utils import filter_users_by_email
from dj_rest_auth.forms import AllAuthPasswordResetForm

from accounts.models import AccountStatus


class EligiblePasswordResetForm(AllAuthPasswordResetForm):
    def clean_email(self):
        email = super().clean_email()
        self.users = [
            user
            for user in filter_users_by_email(email)
            if user.deleted_at is None
            and user.has_usable_password()
            and user.account_status == AccountStatus.ACTIVE
        ]
        return email
