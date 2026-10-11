"""Identity authentication components grouped by responsibility."""

import requests
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from dj_rest_auth.registration.serializers import SocialLoginSerializer
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from rest_framework import serializers

from accounts.services.oauth_accounts import OAuthAccountService
from authentication.oauth.context import consume_context
from common.errors import IdentityAPIError
from common.serializers import StrictInputMixin


class GoogleLoginSerializer(StrictInputMixin, SocialLoginSerializer):
    access_token = None
    id_token = None
    code = serializers.CharField(write_only=True, max_length=4096)
    state = serializers.CharField(write_only=True, max_length=128)
    redirect_uri = serializers.CharField(write_only=True, max_length=500)

    def get_social_login(self, adapter, app, token, response):
        login = super().get_social_login(adapter, app, token, response)
        return OAuthAccountService.resolve_google_account(login, self._get_request())

    def validate(self, attrs):
        request = self.context["request"]
        record = consume_context(request, "google")
        request._request._identity_oauth_context = record
        try:
            result = super().validate(attrs)
        except (OAuth2Error, PermissionDenied) as exc:
            raise IdentityAPIError(
                "OAUTH_AUTHENTICATION_FAILED", "Invalid provider identity."
            ) from exc
        except requests.RequestException as exc:
            raise IdentityAPIError(
                "OAUTH_PROVIDER_UNAVAILABLE", "Provider unavailable.", status_code=503
            ) from exc
        OAuthAccountService.require_active_google_account(result["user"])
        # allauth uses a temporary Django login; REST credentials remain JWT only.
        logout(request._request)
        result["user"]._identity_request = request
        result["user"]._identity_device = "Google OAuth"
        return result
