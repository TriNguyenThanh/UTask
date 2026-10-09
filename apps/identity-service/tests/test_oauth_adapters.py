"""Real PostgreSQL/Redis, mocked external providers. This is not provider acceptance."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.utils import timezone
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from accounts.models import OutboxEvent, User
from authentication.oauth.context import COOKIE, consume_context, context_key, create_context
from authentication.oauth.context import client as context_client
from common.errors import IdentityAPIError
from tests.helpers import create_user, login

pytestmark = pytest.mark.integration


@pytest.fixture
def oauth_settings(settings):
    settings.ROOT_URLCONF = "tests.oauth_urls"
    settings.IDENTITY_GOOGLE_CALLBACK_URI = "https://frontend.test/google"
    settings.IDENTITY_GITHUB_CALLBACK_URI = "https://frontend.test/github"
    settings.IDENTITY_GITHUB_CLIENT_ID = "test-github-client"
    settings.IDENTITY_INTEGRATION_URL = "https://integration.test"
    settings.IDENTITY_INTEGRATION_KEY = "test-service-key"
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APP": {"client_id": "test-google-client", "secret": "test-google-secret", "key": ""}
        }
    }
    return settings


def test_redis_context_has_binding_and_single_consumer():
    state, cookie = create_context("google", "https://frontend.test/google", "verifier", "nonce")
    barrier = Barrier(2)

    def attempt():
        native = APIRequestFactory().post(
            "/", {"state": state, "redirect_uri": "https://frontend.test/google"}, format="json"
        )
        native.COOKIES[COOKIE] = cookie
        request = Request(native, parsers=[JSONParser()])
        barrier.wait(timeout=10)
        try:
            consume_context(request, "google")
            return "accepted"
        except IdentityAPIError as exc:
            return exc.public_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(attempt) for _ in range(2)]
        assert sorted(job.result(timeout=15) for job in jobs) == ["OAUTH_STATE_INVALID", "accepted"]
    assert not context_client().exists(context_key(state))


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres
def test_mocked_google_code_flow_uses_allauth_then_simplejwt(oauth_settings):
    browser = APIClient()
    started = browser.post(
        "/test/oauth/google/start",
        {"redirect_uri": oauth_settings.IDENTITY_GOOGLE_CALLBACK_URI},
        format="json",
    )
    assert started.status_code == 200, started.json()
    query = parse_qs(urlparse(started.json()["data"]["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    data = {
        "code": "mock-google-code",
        "state": query["state"][0],
        "redirect_uri": oauth_settings.IDENTITY_GOOGLE_CALLBACK_URI,
    }
    claims = {
        "sub": "google-test-subject",
        "email": "oauth-student@example.edu.vn",
        "email_verified": True,
        "nonce": query["nonce"][0],
        "given_name": "An",
        "family_name": "Nguyễn",
        "name": "Nguyễn An",
        "picture": "https://lh3.googleusercontent.com/test-avatar",
    }
    with (
        patch(
            "authentication.adapters.oauth.PKCEOAuthClient.get_access_token",
            return_value={
                "access_token": "mock-provider-access",
                "id_token": "mock-provider-id-token",
            },
        ),
        patch("authentication.adapters.oauth._verify_and_decode", return_value=claims) as verify,
    ):
        response = browser.post("/test/oauth/google", data, format="json")
    assert response.status_code == 200, response.json()
    assert verify.call_args.kwargs["verify_signature"] is True
    user = User.objects.get(email=claims["email"])
    assert not user.has_usable_password()
    assert user.is_email_verified
    assert user.profile.first_name == "An"
    assert user.profile.last_name == "Nguyễn"
    assert user.profile.display_name == "Nguyễn An"
    assert user.profile.avatar_url == claims["picture"]
    assert SocialAccount.objects.filter(user=user, provider="google", uid=claims["sub"]).exists()
    assert not SocialToken.objects.exists()
    browser.credentials(HTTP_AUTHORIZATION="Bearer " + response.json()["data"]["access"])
    assert browser.get("/users/me").status_code == 200
    assert browser.delete("/test/oauth/google").status_code == 400
    assert browser.post("/test/oauth/google", data, format="json").status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres
def test_mocked_github_exchange_calls_only_integration(oauth_settings):
    user = create_user()
    browser = APIClient()
    login(browser, user)
    started = browser.post(
        "/test/oauth/github/start",
        {"redirect_uri": oauth_settings.IDENTITY_GITHUB_CALLBACK_URI},
        format="json",
    )
    assert started.status_code == 200, started.json()
    state = parse_qs(urlparse(started.json()["data"]["authorization_url"]).query)["state"][0]

    def proof_response(url, *, json, headers, timeout):
        assert url == "https://integration.test/api/v1/internal/oauth/github/exchange"
        assert headers == {"X-Service-Key": "test-service-key"}
        assert timeout == 5
        assert json["user_id"] == str(user.pk)

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "success": True,
                    "data": {
                        **{
                            key: json[key]
                            for key in ["operation_id", "user_id", "provider", "expires_at"]
                        },
                        "github_user_id": "123456",
                        "github_username": "student",
                        "verified_at": timezone.now().isoformat(),
                    },
                }

        return Response()

    with patch(
        "authentication.adapters.github_identity_proof.requests.post", side_effect=proof_response
    ) as outbound:
        response = browser.post(
            "/test/oauth/github",
            {
                "code": "mock-github-code",
                "state": state,
                "redirect_uri": oauth_settings.IDENTITY_GITHUB_CALLBACK_URI,
            },
            format="json",
        )
    assert response.status_code == 200, response.json()
    assert outbound.call_count == 1
    assert SocialAccount.objects.filter(user=user, provider="github", uid="123456").exists()
    assert OutboxEvent.objects.filter(
        event_type="identity.oauth.github_linked", aggregate_id=user.pk
    ).exists()
    assert browser.delete("/test/oauth/github").status_code == 200
    assert not SocialAccount.objects.filter(user=user, provider="github").exists()
    user.profile.refresh_from_db()
    assert user.profile.github_username is None
