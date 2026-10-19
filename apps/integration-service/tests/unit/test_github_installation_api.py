from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.github_installations.api import (
    GitHubInstallationCompleteView,
    GitHubInstallationStartView,
    GitHubInstallationsView,
    GitHubRepositoriesView,
)
from infrastructure.identity import Principal

pytestmark = pytest.mark.unit


def invoke(view, method, path="/test", data=None, authenticated=True, **kwargs):
    request = getattr(APIRequestFactory(), method)(
        path, data=data, format="json", HTTP_AUTHORIZATION="Bearer actor-token"
    )
    if authenticated:
        force_authenticate(request, user=Principal(uuid4()))
    return view.as_view()(request, **kwargs)


@pytest.mark.parametrize(
    "view,method",
    [
        (GitHubInstallationStartView, "post"),
        (GitHubInstallationCompleteView, "post"),
        (GitHubInstallationsView, "get"),
        (GitHubRepositoriesView, "get"),
    ],
)
def test_endpoints_require_authenticated_identity(view, method):
    kwargs = {"installation_id": "123"} if view == GitHubRepositoriesView else {}
    with patch(
        "common.authentication.IdentityUserClient.current_user",
        side_effect=Exception("must not call"),
    ):
        request = getattr(APIRequestFactory(), method)("/test", data=None, format="json")
        response = view.as_view()(request, **kwargs)
    assert response.status_code in {401, 403}


def test_start_cookie_and_exact_input(settings):
    settings.INTEGRATION_CONSENT_COOKIE_SECURE = True
    with patch(
        "apps.github_installations.api.start_installation",
        return_value=({"installation_url": "https://github.com/new", "expires_at": "now"}, "nonce"),
    ) as start:
        response = invoke(GitHubInstallationStartView, "post")
        assert response.status_code == 200
        cookie = response.cookies["utask_github_installation"]
        assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
        assert response["Cache-Control"] == "private, no-store"
        assert start.call_args.kwargs["bearer"] == "actor-token"
        assert invoke(GitHubInstallationStartView, "post", data={}).status_code == 400
        assert (
            invoke(GitHubInstallationStartView, "post", path="/test?user_id=forged").status_code
            == 400
        )
        assert start.call_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"state": "s" * 43, "installation_id": "123", "setup_action": []},
        {"state": "s" * 43, "installation_id": 123, "setup_action": "install"},
        {
            "state": "s" * 43,
            "installation_id": "123",
            "setup_action": "install",
            "user_id": "forged",
        },
    ],
)
def test_complete_rejects_malformed_input(body):
    with patch("apps.github_installations.api.complete_installation") as complete:
        assert invoke(GitHubInstallationCompleteView, "post", data=body).status_code == 400
        complete.assert_not_called()


def test_complete_deletes_distinct_cookie():
    with patch(
        "apps.github_installations.api.complete_installation", return_value={"status": "ACTIVE"}
    ):
        response = invoke(
            GitHubInstallationCompleteView,
            "post",
            data={"state": "s" * 43, "installation_id": "123", "setup_action": "install"},
        )
    assert response.status_code == 200
    assert response.cookies["utask_github_installation"]["max-age"] == 0


@pytest.mark.parametrize(
    "query",
    ["?user_id=bad", "?page=0", "?page=1&page=2", "?per_page=101", "?page=-1", "?page=10001"],
)
def test_discovery_rejects_arbitrary_or_ambiguous_query(query):
    with patch("apps.github_installations.api.list_installations") as read:
        assert invoke(GitHubInstallationsView, "get", path="/test" + query).status_code == 400
        read.assert_not_called()


def test_discovery_forwards_only_validated_page_and_authenticated_actor():
    with patch(
        "apps.github_installations.api.list_installations",
        return_value={"items": [], "next_page": None},
    ) as read:
        response = invoke(GitHubInstallationsView, "get", path="/test?page=2&per_page=10")
    assert response.status_code == 200
    assert read.call_args.kwargs["page"] == 2 and read.call_args.kwargs["per_page"] == 10
    with patch(
        "apps.github_installations.api.list_repositories",
        return_value={"items": [], "next_page": None},
    ) as read:
        assert invoke(GitHubRepositoriesView, "get", installation_id="123").status_code == 200
        assert read.call_args.kwargs["installation_id"] == "123"
        assert invoke(GitHubRepositoriesView, "get", installation_id="../bad").status_code == 400


def test_provider_401_marks_only_the_access_used_and_403_does_not():
    from apps.github_installations.services import provider_call
    from infrastructure.github_app import GitHubAccessDenied, GitHubAppReauthorizationRequired

    user_id, access = uuid4(), object()
    with patch("apps.github_accounts.credentials.mark_reauthorization_required") as mark:
        assert provider_call(user_id, access, lambda: "ok") == "ok"
        mark.assert_not_called()

        def denied():
            raise GitHubAccessDenied()

        with pytest.raises(GitHubAccessDenied):
            provider_call(user_id, access, denied)
        mark.assert_not_called()

        def unauthorized():
            raise GitHubAppReauthorizationRequired()

        with pytest.raises(GitHubAppReauthorizationRequired):
            provider_call(user_id, access, unauthorized)
        mark.assert_called_once_with(user_id=user_id, access=access)
