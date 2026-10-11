"""allauth hooks for profile/lifecycle and encrypted Notification handoff."""

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.http import HttpResponse

from accounts.models import AccountStatus
from accounts.services.registration import RegistrationService


class IdentityAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        return RegistrationService.prepare_pending_account(user, commit)

    def pre_login(self, request, user, *, signup=False, **kwargs):
        # Mandatory email verification stops signup before any login/session issuance.
        if (
            signup
            and user.account_status == AccountStatus.PENDING_ACTIVATION
            and user.deleted_at is None
        ):
            return None
        return super().pre_login(request, user, signup=signup, **kwargs)

    def respond_email_verification_sent(self, request, user):
        return HttpResponse(status=204)

    def get_email_confirmation_url(self, request, emailconfirmation):
        return f"{settings.IDENTITY_FRONTEND_URL}/auth/activate?key={emailconfirmation.key}"

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        return RegistrationService.send_activation_confirmation(
            emailconfirmation,
            lambda: super(IdentityAccountAdapter, self).send_confirmation_mail(
                request, emailconfirmation, signup
            ),
        )

    def send_mail(self, template_prefix, email, context):
        RegistrationService.queue_account_mail(template_prefix, context)

    def confirm_email(self, request, email_address):
        return RegistrationService.confirm_activation(
            request,
            email_address,
            lambda: super(IdentityAccountAdapter, self).confirm_email(request, email_address),
        )
