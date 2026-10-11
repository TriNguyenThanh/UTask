"""allauth social hooks only. No unfinished provider endpoints are exposed."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from accounts.services.oauth_accounts import OAuthAccountService


class IdentitySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # GitHub requires Integration's proof contract, not an allauth outbound provider.
        OAuthAccountService.validate_google_identity(sociallogin)

    def save_user(self, request, sociallogin, form=None):
        return OAuthAccountService.register_google_student(
            request,
            sociallogin,
            lambda: super(IdentitySocialAccountAdapter, self).save_user(request, sociallogin, form),
        )
