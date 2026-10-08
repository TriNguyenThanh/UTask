"""Identity authentication components grouped by responsibility."""

import secrets

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter, _verify_and_decode
from allauth.socialaccount.providers.oauth2.client import OAuth2Client, OAuth2Error
from django.conf import settings


class BoundGoogleAdapter(GoogleOAuth2Adapter):
    def _decode_id_token(self, app, id_token):
        claims = _verify_and_decode(app, id_token, verify_signature=True)
        if claims.get("email_verified") is not True or not secrets.compare_digest(
            str(claims.get("nonce", "")), self.request._identity_oauth_context["nonce"]
        ):
            raise OAuth2Error("Unverified email or invalid nonce.")
        return claims

    def get_callback_url(self, request, app):
        return settings.IDENTITY_GOOGLE_CALLBACK_URI


class PKCEOAuthClient(OAuth2Client):
    def get_access_token(self, code, pkce_code_verifier=None, extra_data=None):
        return super().get_access_token(
            code,
            pkce_code_verifier=self.request._identity_oauth_context["verifier"],
            extra_data=extra_data,
        )
