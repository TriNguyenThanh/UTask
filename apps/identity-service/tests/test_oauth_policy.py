from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import Resolver404, resolve

from authentication.adapters.social import IdentitySocialAccountAdapter


@pytest.mark.unit
@pytest.mark.parametrize(
    "provider,email,verified",
    [
        ("github", "a@example.edu.vn", True),
        ("google", "a@example.com", True),
        ("google", "a@example.edu.vn", False),
    ],
)
def test_social_hook_denies_untrusted_provider_or_student_email(provider, email, verified):
    social = SimpleNamespace(
        account=SimpleNamespace(provider=provider),
        email_addresses=[SimpleNamespace(email=email, verified=verified)],
        is_existing=False,
    )
    with pytest.raises(PermissionDenied):
        IdentitySocialAccountAdapter().pre_social_login(RequestFactory().get("/"), social)


@pytest.mark.unit
def test_social_hook_accepts_verified_educational_google_identity():
    social = SimpleNamespace(
        account=SimpleNamespace(provider="google"),
        email_addresses=[SimpleNamespace(email="a@example.edu.vn", verified=True)],
        is_existing=False,
    )
    IdentitySocialAccountAdapter().pre_social_login(RequestFactory().get("/"), social)


@pytest.mark.contract
@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/auth/oauth/google",
        "/api/v1/auth/oauth/google/start",
        "/api/v1/auth/oauth/github",
        "/api/v1/auth/oauth/github/start",
        "/api/v1/registration/",
        "/api/v1/token/verify/",
    ],
)
def test_unfinished_and_uncontracted_routes_are_closed(route):
    with pytest.raises(Resolver404):
        resolve(route)
