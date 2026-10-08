"""Framework loading and route ownership after moving the Identity modules."""

import importlib

import pytest
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from dj_rest_auth.app_settings import api_settings as rest_auth_settings
from django.conf import settings
from django.contrib.auth import get_backends, get_user_model
from django.urls import clear_url_caches, resolve, reverse
from django.utils.module_loading import import_string
from rest_framework.settings import api_settings as drf_settings

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "setting,module,name",
    [
        ("LOGIN_SERIALIZER", "authentication.serializers.auth", "LoginRequestSerializer"),
        ("USER_DETAILS_SERIALIZER", "accounts.serializers.profiles", "CurrentUserSerializer"),
        (
            "JWT_TOKEN_CLAIMS_SERIALIZER",
            "authentication.serializers.auth",
            "SessionTokenSerializer",
        ),
        (
            "REGISTER_SERIALIZER",
            "authentication.serializers.registration",
            "StudentRegisterSerializer",
        ),
        (
            "PASSWORD_RESET_SERIALIZER",
            "authentication.serializers.passwords",
            "IdentityPasswordResetSerializer",
        ),
        (
            "PASSWORD_RESET_CONFIRM_SERIALIZER",
            "authentication.serializers.passwords",
            "IdentityPasswordResetConfirmSerializer",
        ),
        (
            "PASSWORD_CHANGE_SERIALIZER",
            "authentication.serializers.passwords",
            "IdentityPasswordChangeSerializer",
        ),
    ],
)
def test_rest_auth_loads_canonical_serializer(setting, module, name):
    cls = getattr(rest_auth_settings, setting)
    assert cls.__module__ == module
    assert cls.__name__ == name
    assert import_string(settings.REST_AUTH[setting]) is cls


def test_auth_framework_loads_canonical_hooks_and_unchanged_model_owner():
    assert get_account_adapter().__class__.__module__ == "authentication.adapters.account"
    assert get_social_adapter().__class__.__module__ == "authentication.adapters.social"
    assert [backend.__class__.__module__ for backend in get_backends()] == [
        "axes.backends",
        "authentication.adapters.password_authentication",
    ]
    assert (
        drf_settings.DEFAULT_AUTHENTICATION_CLASSES[0].__module__
        == "authentication.adapters.access_token_authentication"
    )
    assert drf_settings.DEFAULT_RENDERER_CLASSES[0].__module__ == "common.renderers"
    assert drf_settings.EXCEPTION_HANDLER.__module__ == "common.exception_handler"
    assert (
        rest_auth_settings.JWT_TOKEN_CLAIMS_SERIALIZER.token_class.__module__
        == "authentication.adapters.session_tokens"
    )
    for setting in ("AXES_USERNAME_CALLABLE", "AXES_LOCKOUT_CALLABLE"):
        assert (
            import_string(getattr(settings, setting)).__module__
            == "authentication.adapters.login_lockout"
        )
    validators = [import_string(config["NAME"]) for config in settings.AUTH_PASSWORD_VALIDATORS]
    assert validators[-1].__module__ == "authentication.adapters.password_validation"
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model()._meta.app_label == "accounts"
    assert "messaging" not in settings.INSTALLED_APPS


@pytest.mark.parametrize(
    "name,path,module",
    [
        ("identity-login", "/api/v1/auth/login", "authentication.views.auth"),
        ("identity-refresh", "/api/v1/auth/refresh", "authentication.views.auth"),
        ("identity-current-user", "/api/v1/users/me", "accounts.views.profiles"),
        ("identity-register", "/api/v1/auth/register", "authentication.views.registration"),
        ("identity-activate", "/api/v1/auth/activate", "authentication.views.registration"),
        ("identity-logout", "/api/v1/auth/logout", "authentication.views.devices"),
        ("identity-sessions", "/api/v1/auth/sessions", "authentication.views.devices"),
        (
            "identity-password-change",
            "/api/v1/auth/password-change",
            "dj_rest_auth.views",
        ),
    ],
)
def test_routes_keep_path_and_load_the_owned_view(name, path, module):
    assert reverse(name) == path
    assert resolve(path).func.view_class.__module__ == module


@pytest.mark.parametrize(
    "google,github", [(False, False), (True, False), (False, True), (True, True)]
)
def test_oauth_flags_keep_routes_closed_or_open_as_before(settings, google, github):
    settings.IDENTITY_GOOGLE_ENABLED = google
    settings.IDENTITY_GITHUB_ENABLED = github
    urls = importlib.import_module("authentication.urls")
    try:
        importlib.reload(urls)
        paths = {str(pattern.pattern) for pattern in urls.urlpatterns}
        assert ("api/v1/auth/oauth/google" in paths) is google
        assert ("api/v1/auth/oauth/github" in paths) is github
    finally:
        settings.IDENTITY_GOOGLE_ENABLED = False
        settings.IDENTITY_GITHUB_ENABLED = False
        importlib.reload(urls)
        clear_url_caches()
