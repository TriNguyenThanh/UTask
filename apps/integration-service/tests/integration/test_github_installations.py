from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.exceptions import ParseError

from apps.github_accounts.consent import ConsentConflict, lock_generation
from apps.github_installations import services
from apps.github_installations.models import GitHubInstallation, GitHubPendingInstallation
from infrastructure.github_app import GitHubAccessDenied, GitHubNotFound

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def flow(settings):
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    settings.INTEGRATION_GITHUB_SETUP_URI = "https://utask.test/installations/callback"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_GITHUB_APP_ID = "42"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    access = SimpleNamespace(access_token="private-token", version=1, generation=0)
    item = {
        "installation_id": "123",
        "app_id": "42",
        "account": {"id": "1", "login": "octo", "type": "User"},
        "repository_selection": "selected",
        "suspended_at": None,
    }
    with (
        patch.object(services, "get_access_token", return_value=access),
        patch.object(services, "assert_access_current") as fence,
        patch.object(
            services.GitHubAppClient,
            "installations",
            return_value={"items": [item], "next_page": None},
        ) as installations,
        patch.object(
            services.GitHubAppClient, "repositories", return_value={"items": [], "next_page": None}
        ) as repositories,
    ):
        yield SimpleNamespace(
            user_id=uuid4(),
            item=item,
            access=access,
            fence=fence,
            installations=installations,
            repositories=repositories,
        )


def begin(flow):
    data, nonce = services.start_installation(user_id=flow.user_id, bearer="bearer")
    state = parse_qs(urlsplit(data["installation_url"]).query)["state"][0]
    return dict(
        user_id=flow.user_id,
        bearer="bearer",
        state=state,
        nonce=nonce,
        installation_id="123",
        setup_action="install",
    )


def test_success_one_use_nonce_and_selected_metadata(flow):
    arguments = begin(flow)
    stored = str(list(GitHubPendingInstallation.objects.values()))
    assert arguments["state"] not in stored and arguments["nonce"] not in stored
    assert services.complete_installation(**arguments)["status"] == "ACTIVE"
    assert GitHubInstallation.objects.get().installation_id == "123"
    flow.repositories.assert_called_once_with("private-token", "123", page=1, per_page=1)
    with pytest.raises(ParseError):
        services.complete_installation(**arguments)
    assert GitHubPendingInstallation.objects.get().consumed_at is not None


@pytest.mark.parametrize("fault", ["nonce", "bearer", "actor", "expired", "new-start", "unlink"])
def test_invalid_bindings_do_not_call_provider(flow, fault):
    arguments = begin(flow)
    if fault in {"nonce", "bearer"}:
        arguments[fault] = "x" * 43
    elif fault == "actor":
        arguments["user_id"] = uuid4()
    elif fault == "expired":
        GitHubPendingInstallation.objects.update(expires_at=timezone.now())
    elif fault == "new-start":
        begin(flow)
    else:
        from django.db import transaction

        with transaction.atomic():
            generation = lock_generation(flow.user_id)
            generation.generation += 1
            generation.save()
    with pytest.raises(ParseError):
        services.complete_installation(**arguments)
    flow.installations.assert_not_called()


def test_request_does_not_claim_membership_or_call_provider(flow):
    arguments = begin(flow) | {"setup_action": "request"}
    assert services.complete_installation(**arguments) == {
        "status": "PENDING_APPROVAL",
        "installation_id": "123",
    }
    flow.installations.assert_not_called()
    flow.repositories.assert_not_called()
    assert not GitHubInstallation.objects.exists()


@pytest.mark.parametrize(
    "fault,error",
    [
        ("missing", GitHubNotFound),
        ("suspended", GitHubAccessDenied),
        ("other-app", GitHubAccessDenied),
    ],
)
def test_membership_suspension_and_app_checked(flow, fault, error):
    arguments = begin(flow)
    if fault == "missing":
        flow.installations.return_value = {"items": [], "next_page": None}
    elif fault == "suspended":
        flow.item["suspended_at"] = "2026-01-01T00:00:00Z"
    else:
        flow.item["app_id"] = "999"
    with pytest.raises(error):
        services.complete_installation(**arguments)
    assert not GitHubInstallation.objects.exists()
    flow.repositories.assert_not_called()


def test_later_installation_start_fences_inflight_completion(flow):
    arguments = begin(flow)

    def repositories(*args, **kwargs):
        begin(flow)
        return {"items": [], "next_page": None}

    flow.repositories.side_effect = repositories
    with pytest.raises(ConsentConflict):
        services.complete_installation(**arguments)
    assert not GitHubInstallation.objects.exists()


def test_discovery_does_not_trust_cached_installation(flow):
    services.remember_installation(flow.item)
    flow.installations.return_value = {"items": [], "next_page": None}
    with pytest.raises(GitHubNotFound):
        services.list_repositories(user_id=flow.user_id, installation_id="123", page=1, per_page=30)
    flow.repositories.assert_not_called()


def test_paginated_membership_and_current_credential_fence(flow):
    flow.installations.side_effect = [
        {"items": [], "next_page": 2},
        {"items": [flow.item], "next_page": None},
    ]
    assert services.list_repositories(
        user_id=flow.user_id, installation_id="123", page=2, per_page=10
    ) == {"items": [], "next_page": None}
    assert flow.installations.call_count == 2
    flow.fence.assert_called_once_with(user_id=flow.user_id, access=flow.access)


@pytest.mark.parametrize(
    "event,status",
    [
        ("deleted", "DELETED"),
        ("suspend", "SUSPENDED"),
        ("unsuspend", "STALE"),
        ("repositories_removed", "STALE"),
    ],
)
def test_webhook_invalidates_hint_only(flow, event, status):
    services.remember_installation(flow.item)
    row = services.invalidate_installation(
        installation_id="123", event=event, removed_repository_ids=["99"]
    )
    assert row.status == status and row.source_version == 2
    assert services.invalidate_installation(installation_id="999", event=event) is None


@pytest.mark.django_db(transaction=True)
def test_duplicate_completion_provider_called_once(flow):
    arguments = begin(flow)
    barrier = Barrier(2)

    def complete():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                services.complete_installation(**arguments)
                return "ok"
            except ParseError:
                return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(complete), pool.submit(complete)]
        assert sorted(result.result(timeout=15) for result in results) == ["ok", "rejected"]
    flow.repositories.assert_called_once()


def test_unbounded_membership_scan_fails_closed(flow):
    from infrastructure.github_oauth import GitHubOAuthUnavailable

    flow.installations.side_effect = lambda token, page, per_page: {
        "items": [],
        "next_page": page + 1,
    }
    with pytest.raises(GitHubOAuthUnavailable):
        services.list_repositories(user_id=flow.user_id, installation_id="123", page=1, per_page=30)
    assert flow.installations.call_count == 10
    flow.repositories.assert_not_called()


def test_provider_failure_consumes_state_and_does_not_save_metadata(flow):
    from infrastructure.github_oauth import GitHubOAuthUnavailable

    arguments = begin(flow)
    flow.repositories.side_effect = GitHubOAuthUnavailable()
    with pytest.raises(GitHubOAuthUnavailable):
        services.complete_installation(**arguments)
    with pytest.raises(ParseError):
        services.complete_installation(**arguments)
    assert not GitHubInstallation.objects.exists()


def test_credential_change_fails_before_provider(flow):
    arguments = begin(flow)
    flow.access.version += 1
    with pytest.raises(ConsentConflict):
        services.complete_installation(**arguments)
    flow.installations.assert_not_called()
