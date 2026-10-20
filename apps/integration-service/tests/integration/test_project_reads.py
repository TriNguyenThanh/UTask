"""Real credential/database fences with bounded, fake Work/GitHub HTTP."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.github_accounts.consent import lock_generation
from apps.github_accounts.credentials import ReauthorizationRequired, store_credential
from apps.github_accounts.models import GitHubAccount, GitHubCredential
from apps.github_connections import services
from apps.github_connections.errors import VersionConflict
from apps.github_connections.models import ConnectionOperation, ProjectConnection
from infrastructure.github_app import GitHubAppReauthorizationRequired
from infrastructure.work import WorkAccessDenied, WorkUnavailable
from tests.contract.test_github_app_contract import validate
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]
DATE = "2026-10-20T00:00:00Z"
SHA = "a" * 40
REPO = {"repo_id": "12", "repo_owner": "octo", "repo_name": "demo", "default_branch": "main"}


def response(payload, status=200):
    context = MagicMock()
    context.__enter__.return_value.status_code = status
    context.__enter__.return_value.headers = {}
    context.__enter__.return_value.iter_content.return_value = [json.dumps(payload).encode()]
    return context


@pytest.fixture
def flow(settings):
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_AI_CONTEXT_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "42"
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]
    settings.INTEGRATION_WORK_URL = "http://work.test"
    settings.INTEGRATION_WORK_SERVICE_KEY = "w" * 32
    connector, caller, project = uuid4(), uuid4(), uuid4()
    with transaction.atomic():
        generation = lock_generation(connector)
        GitHubAccount.objects.create(
            user_id=connector,
            github_user_id="123",
            github_username="Octo",
            verified_at=timezone.now(),
        )
        store_credential(
            user_id=connector, identity=token_identity(access_token="connector-private-token")
        )
    row = ProjectConnection.objects.create(
        project_id=project,
        user_id=connector,
        installation_id="55",
        **REPO,
        status="CONNECTED",
        generation=1,
        current_operation="accepted-connect",
        accepted_operation="accepted-connect",
        accepted_generation=1,
        source_version=2,
        credential_generation=generation.generation,
        revision=1,
    )
    state = SimpleNamespace(
        row=row,
        connector=connector,
        caller=caller,
        project=project,
        allowed=True,
        work_status=200,
        partial=False,
        provider_status=200,
        race=None,
        provider_calls=[],
    )

    def transport(method, url, **kwargs):
        assert not connection.in_atomic_block
        if url.startswith("http://work.test/"):
            assert kwargs["headers"]["Authorization"] == "Bearer reader-token"
            assert kwargs["json"] == {"action": "github.read"}
            return response(
                {
                    "success": True,
                    "data": {
                        "project_id": str(project),
                        "action": "github.read",
                        "allowed": state.allowed,
                    },
                },
                state.work_status,
            )
        assert url.startswith("https://api.github.com/")
        assert kwargs["headers"]["Authorization"] == "Bearer connector-private-token"
        state.provider_calls.append(url)
        if state.race:
            race, state.race = state.race, None
            race()
        if state.provider_status != 200:
            return response({}, state.provider_status)
        if url.endswith("/repositories/12"):
            return response(
                {
                    "id": 12,
                    "owner": {"login": "octo"},
                    "name": "demo",
                    "default_branch": "main",
                    "private_secret": "discard",
                }
            )
        if url.endswith("/branches/main"):
            return response({"name": "main", "commit": {"sha": SHA}, "secret": "discard"})
        if url.endswith("/commits"):
            return response(
                [
                    {
                        "sha": SHA,
                        "commit": {"message": "Fix bug\nprivate body", "committer": {"date": DATE}},
                        "html_url": f"https://github.com/octo/demo/commit/{SHA}",
                        "token": "raw-provider-secret",
                    }
                ]
            )
        if url.endswith("/pulls"):
            return response(
                [
                    {
                        "number": 3,
                        "title": "Fix bug",
                        "state": "open",
                        "html_url": "https://github.com/octo/demo/pull/3",
                        "updated_at": DATE,
                    }
                ]
            )
        if url.endswith("/issues"):
            return response([], 403 if state.partial else 200)
        raise AssertionError(f"Unexpected request path: {url}")

    with (
        patch("infrastructure.work.requests.request", side_effect=transport) as http,
        patch.object(
            services.GitHubProjectClient,
            "find_repository",
            return_value={"installation_id": "55", **REPO},
        ) as discovery,
    ):
        state.http, state.discovery = http, discovery
        yield state


def context(flow):
    return services.context_document(project_id=flow.project, bearer="reader-token")


def reference(flow, **changes):
    return services.verify_reference(
        project_id=flow.project,
        body={"repo_id": "12", "generation": 1, "link_type": "BRANCH", "ref_id": "main", **changes},
    )


def test_authorized_missing_context_matches_contract_without_provider(flow):
    flow.row.delete()
    document = context(flow)
    validate("GitHubContextDocument", document)
    assert document["status"] == "missing"
    assert document["source_version"] is None
    assert document["data"]["mapping_status"] == "DISCONNECTED"
    assert flow.http.call_count == 1
    flow.discovery.assert_not_called()


def test_work_denies_before_connector_credential_or_provider_access(flow):
    flow.allowed = False
    with patch.object(services, "get_access_token") as credential:
        with pytest.raises(WorkAccessDenied):
            context(flow)
    credential.assert_not_called()
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


@pytest.mark.parametrize("status", [401, 403, 503])
def test_work_failure_never_reads_provider(flow, status):
    flow.work_status = status
    with pytest.raises(WorkUnavailable):
        context(flow)
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


@pytest.mark.parametrize("partial", [False, True])
def test_context_uses_connector_credential_and_filters_provider_fields(flow, partial):
    flow.partial = partial
    document = context(flow)
    validate("GitHubContextDocument", document)
    assert document["status"] == ("partial" if partial else "available")
    assert bool(document["warning"]) == partial
    assert document["source_version"] == "2"
    assert document["data"]["mapping_status"] == "CONNECTED"
    assert document["data"]["commits"][0]["title"] == "Fix bug"
    assert document["data"]["pull_requests"][0]["status"] == "OPEN"
    assert "private" not in json.dumps(document)
    assert "raw-provider-secret" not in json.dumps(document)
    assert not GitHubCredential.objects.filter(user_id=flow.caller).exists()
    flow.discovery.assert_called_once_with("connector-private-token", "12")


def test_revalidation_returns_explicit_stale_without_provider(flow):
    ProjectConnection.objects.filter(pk=flow.project).update(needs_revalidation=True)
    document = context(flow)
    validate("GitHubContextDocument", document)
    assert document["status"] == "stale"
    assert document["data"]["mapping_status"] == "REAUTH_REQUIRED"
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


@pytest.mark.parametrize("read", [context, reference])
def test_pending_operation_blocks_connected_snapshot(flow, read):
    ProjectConnection.objects.filter(pk=flow.project).update(current_operation="pending")
    ConnectionOperation.objects.create(
        project_id=flow.project,
        operation_id="pending",
        user_id=flow.connector,
        action="CONNECT",
        payload_hash="a" * 64,
        expected_generation=1,
        generation=2,
        expires_at=timezone.now() + timedelta(hours=1),
        retain_until=timezone.now() + timedelta(days=30),
    )
    with pytest.raises(VersionConflict):
        read(flow)
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


@pytest.mark.parametrize("read", [context, reference])
def test_revoked_connector_has_no_provider_access(flow, read):
    GitHubCredential.objects.filter(user_id=flow.connector).update(status="REVOKED")
    with pytest.raises(ReauthorizationRequired):
        read(flow)
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


@pytest.mark.parametrize("read", [context, reference])
def test_connection_generation_change_during_provider_call_discards_old_result(flow, read):
    def advance():
        ProjectConnection.objects.filter(pk=flow.project).update(
            generation=F("generation") + 1,
            revision=F("revision") + 1,
        )

    flow.race = advance
    with pytest.raises(VersionConflict):
        read(flow)
    assert flow.provider_calls
    flow.row.refresh_from_db()
    assert flow.row.generation == 2


@pytest.mark.parametrize("read", [context, reference])
def test_credential_generation_change_during_provider_call_discards_result(flow, read):
    def revoke():
        with transaction.atomic():
            generation = lock_generation(flow.connector)
            generation.generation += 1
            generation.save(update_fields=["generation"])

    flow.race = revoke
    with pytest.raises(ReauthorizationRequired):
        read(flow)


@pytest.mark.parametrize("read", [context, reference])
def test_provider_revoked_session_persists_reauthorization(flow, read):
    flow.provider_status = 401
    with pytest.raises(GitHubAppReauthorizationRequired):
        read(flow)
    assert GitHubCredential.objects.get(pk=flow.connector).status == "REAUTH_REQUIRED"


@pytest.mark.parametrize("changes", [{"repo_id": "99"}, {"generation": 2}])
def test_reference_rejects_wrong_repository_or_generation_before_provider(flow, changes):
    with pytest.raises(VersionConflict):
        reference(flow, **changes)
    flow.discovery.assert_not_called()
    assert not flow.provider_calls


def test_reference_fact_is_safe_and_matches_contract(flow):
    fact = reference(flow)
    validate("ReferenceFact", fact)
    assert fact["project_id"] == str(flow.project)
    assert fact["repo_id"] == "12"
    assert fact["generation"] == 1
    assert fact["source_version"] == 2
    assert fact["is_verified"] is True
    assert fact["url"] == "https://github.com/octo/demo/tree/main"
    assert "secret" not in json.dumps(fact)
    flow.discovery.assert_called_once_with("connector-private-token", "12")
