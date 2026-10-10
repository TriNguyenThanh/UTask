"""Feature-gated OAuth endpoints; provider HTTP belongs to allauth or Integration."""

from dj_rest_auth.app_settings import api_settings
from dj_rest_auth.registration.views import SocialAccountDisconnectView, SocialLoginView
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.services.oauth_accounts import OAuthAccountService
from authentication.adapters.access_token_authentication import IdentityJWTAuthentication
from authentication.adapters.oauth import BoundGoogleAdapter, PKCEOAuthClient
from authentication.oauth.context import COOKIE
from authentication.serializers.oauth import GoogleLoginSerializer


class OAuthDisconnectView(SocialAccountDisconnectView):
    http_method_names = ["delete", "options"]

    def delete(self, request, provider):
        OAuthAccountService.unlink_account(
            request,
            provider,
            lambda pk: super(OAuthDisconnectView, self).post(request, pk=pk),
        )
        return Response({"detail": "Account unlinked."})


@extend_schema_view(
    post=extend_schema(auth=[], responses=api_settings.JWT_SERIALIZER),
    delete=extend_schema(request=None, responses={200: None}),
)
class GoogleLoginView(SocialLoginView, OAuthDisconnectView):
    http_method_names = ["post", "delete", "options"]

    def get_authenticators(self):
        return (
            [IdentityJWTAuthentication()]
            if self.request and self.request.method == "DELETE"
            else []
        )

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "DELETE" else [AllowAny()]

    adapter_class = BoundGoogleAdapter
    client_class = PKCEOAuthClient
    serializer_class = GoogleLoginSerializer

    @property
    def callback_url(self):
        return settings.IDENTITY_GOOGLE_CALLBACK_URI


class OAuthStartView(APIView):
    throttle_scope = "oauth"

    def get_permissions(self):
        return (
            [AllowAny()] if self.kwargs.get("provider") == "google" else super().get_permissions()
        )

    @extend_schema(
        request=inline_serializer(
            "OAuthStartInput",
            fields={
                "redirect_uri": serializers.CharField(),
            },
        ),
        responses=inline_serializer(
            "OAuthStartData",
            fields={
                "authorization_url": serializers.URLField(),
                "expires_in": serializers.IntegerField(),
            },
        ),
    )
    def post(self, request, provider):
        expected = (
            settings.IDENTITY_GOOGLE_CALLBACK_URI
            if provider == "google"
            else settings.IDENTITY_GITHUB_CALLBACK_URI
        )
        if set(request.data) != {"redirect_uri"} or request.data["redirect_uri"] != expected:
            raise serializers.ValidationError({"redirect_uri": "Redirect URI is not allowed."})
        url, cookie = OAuthAccountService.start_authorization(request, provider, expected)
        response = Response({"authorization_url": url, "expires_in": 600})
        response.set_cookie(
            COOKIE,
            cookie,
            max_age=600,
            secure=True,
            httponly=True,
            samesite="Lax",
            path="/api/auth",
        )
        return response


@extend_schema_view(delete=extend_schema(request=None, responses={200: None}))
class GitHubLinkView(OAuthDisconnectView):
    http_method_names = ["post", "delete", "options"]
    throttle_scope = "oauth"

    @extend_schema(
        request=inline_serializer(
            "GitHubLinkInput",
            fields={
                "code": serializers.CharField(),
                "state": serializers.CharField(),
                "redirect_uri": serializers.CharField(),
            },
        ),
        responses=inline_serializer(
            "GitHubLinkData",
            fields={
                "provider": serializers.CharField(),
                "github_username": serializers.CharField(),
                "linked_at": serializers.DateTimeField(),
            },
        ),
    )
    def post(self, request, provider=None):
        if set(request.data) != {"code", "state", "redirect_uri"} or not isinstance(
            request.data["code"], str
        ):
            raise serializers.ValidationError("Expected code, state and redirect_uri.")
        proof = OAuthAccountService.link_github_account(request)
        return Response(
            {
                "provider": "GITHUB",
                "github_username": proof["github_username"],
                "linked_at": proof["linked_at"],
            }
        )
