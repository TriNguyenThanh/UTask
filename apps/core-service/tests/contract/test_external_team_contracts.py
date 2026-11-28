"""External team contract tests (Team Web, Team AI, Team Integration, Team Notification)."""

from __future__ import annotations

import json
from uuid import uuid4

import jwt
import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountStatus, GlobalRoleCode, User, UserSession
from apps.integrations.models import GitHubConnectionOperation
from apps.messaging.models import OutboxEvent
from apps.projects.models import Project, ProjectMember, State
from apps.tasks.models import Task, TaskAssignment

pytestmark = [pytest.mark.contract, pytest.mark.django_db]

ENVELOPE_KEYS = {"success", "message", "data", "meta", "error"}
PASSWORD = "StrongPass123!"
WORK_AI_KEY = "a" * 40
WORK_INTEGRATION_KEY = "i" * 40


def _create_user(
    *,
    role: str = GlobalRoleCode.STUDENT,
    status: str = AccountStatus.ACTIVE,
    deleted_at=None,
    first_name: str = "An",
    last_name: str = "Nguyễn",
) -> User:
    suffix = uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"contract_{suffix}@utask.edu.vn",
        username=f"contract_{suffix}",
        password=PASSWORD,
        first_name=first_name,
        last_name=last_name,
        global_role_code=role,
        account_status=status,
        deleted_at=deleted_at,
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def _login(user: User) -> tuple[str, UserSession, dict]:
    client = APIClient()
    response = client.post(
        "/api/auth/login",
        {"email": user.email, "password": PASSWORD},
        format="json",
        secure=True,
    )
    assert response.status_code == 200, response.content
    body = response.json()
    session = UserSession.objects.filter(user=user).order_by("-created_at").first()
    assert session is not None
    return body["data"]["access"], session, response


def _create_project_with_member(leader: User, member: User | None = None):
    now = timezone.now()
    project = Project.objects.create(
        identifier=f"P{uuid4().hex[:6].upper()}",
        name="Contract Verification Project",
        description="Project for external contract verification",
        target_goals="Verify AI, Integration, Notification contracts",
        classroom_group_id=str(uuid4()),
    )
    ProjectMember.objects.create(
        project=project,
        user_id=leader.pk,
        role=ProjectMember.Role.LEADER,
        status=ProjectMember.Status.ACTIVE,
        weekly_capacity=20,
        joined_at=now,
    )
    if member is not None:
        ProjectMember.objects.create(
            project=project,
            user_id=member.pk,
            role=ProjectMember.Role.MEMBER,
            status=ProjectMember.Status.ACTIVE,
            weekly_capacity=15,
            joined_at=now,
        )
    state = State.objects.create(
        project=project,
        name="To Do",
        slug="to-do",
        color="#94A3B8",
        sequence=10000,
        group=State.Group.UNSTARTED,
        is_default=True,
    )
    task = Task.objects.create(
        project=project,
        sequence_id=1,
        state=state,
        title="Verify external contracts",
        created_by_user_id=leader.pk,
    )
    return project, state, task


# ---------------------------------------------------------------------------
# Team Web Contracts
# ---------------------------------------------------------------------------


def test_team_web_auth_docs_returns_200_and_sets_csrf_cookie():
    client = APIClient()
    response = client.get("/api/auth/docs/", secure=True)

    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert response.cookies["csrftoken"].value


@pytest.mark.parametrize(
    "path",
    [
        "/healthz",
        "/api/auth/healthz",
        "/api/classroom/healthz",
        "/api/work/healthz",
    ],
)
def test_team_web_healthz_probes_return_200_ok(path):
    response = APIClient().get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_team_web_login_returns_envelope_and_refresh_cookie_path():
    user = _create_user()
    _, _, response = _login(user)

    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["access"]
    assert body["data"]["user"]["id"] == str(user.pk)
    assert response.headers["Cache-Control"] == "no-store"

    cookie = response.cookies["refresh_token"]
    assert cookie["path"] == "/api/auth"
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"] == "Lax"


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/users/me",
        "/api/classroom/courses/",
        "/api/work/projects/",
    ],
)
def test_team_web_unified_401_error_codes_across_all_domains(path):
    user = _create_user()
    access, session, _ = _login(user)

    # 1. Missing credentials -> AUTHENTICATION_REQUIRED
    anon = APIClient()
    missing = anon.get(path)
    assert missing.status_code == 401
    missing_body = missing.json()
    assert set(missing_body) == ENVELOPE_KEYS
    assert missing_body["success"] is False
    assert missing_body["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # 2. Malformed/invalid Bearer -> INVALID_TOKEN
    invalid = APIClient()
    invalid.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-jwt")
    bad = invalid.get(path)
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_TOKEN"

    # 3. Revoked UserSession -> TOKEN_REVOKED
    session.is_revoked = True
    session.revoked_at = timezone.now()
    session.revoked_reason = "LOGOUT"
    session.save(update_fields=("is_revoked", "revoked_at", "revoked_reason"))

    revoked_client = APIClient()
    revoked_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    revoked = revoked_client.get(path)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "TOKEN_REVOKED"


@pytest.mark.parametrize(
    "path",
    [
        "/openapi/",
        "/api/auth/openapi/",
        "/api/classroom/openapi/",
        "/api/work/openapi/",
    ],
)
def test_team_web_openapi_endpoints_return_200_valid_schema(path):
    response = APIClient().get(path, HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"] == "3.1.0"
    assert isinstance(schema["paths"], dict) and len(schema["paths"]) > 0


# ---------------------------------------------------------------------------
# Team AI Contracts
# ---------------------------------------------------------------------------


def test_team_ai_jwks_root_and_auth_prefix_return_raw_keys_and_verify_jwt():
    user = _create_user()
    access, _, _ = _login(user)

    root_resp = APIClient().get("/.well-known/jwks.json")
    prefixed_resp = APIClient().get("/api/auth/.well-known/jwks.json")

    assert root_resp.status_code == 200
    assert prefixed_resp.status_code == 200
    root_body = root_resp.json()
    assert set(root_body) == {"keys"}
    assert "success" not in root_body
    assert root_body == prefixed_resp.json()
    assert len(root_body["keys"]) == 1

    jwk = root_body["keys"][0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    claims = jwt.decode(
        access,
        key=public_key,
        algorithms=["RS256"],
        audience="utask-platform",
        issuer="https://identity.utask.internal",
    )
    assert claims["sub"] == str(user.pk)


def test_team_ai_session_status_enforces_service_key_and_live_session(settings):
    user = _create_user()
    access, session, _ = _login(user)
    ai_key = settings.IDENTITY_SERVICE_KEYS["ai"]
    route = "/api/v1/internal/auth/session-status"

    # Missing or wrong X-Service-Key is rejected with 403 SERVICE_ACCESS_DENIED.
    assert APIClient().post(route, {}, format="json").status_code == 403
    wrong_key = APIClient().post(
        route,
        {},
        format="json",
        HTTP_X_SERVICE_KEY="wrong-key",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert wrong_key.status_code == 403
    assert wrong_key.json()["error"]["code"] == "SERVICE_ACCESS_DENIED"

    # Live session returns active=True.
    active = APIClient().post(
        route,
        {},
        format="json",
        HTTP_X_SERVICE_KEY=ai_key,
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert active.status_code == 200
    assert active.json()["data"] == {"active": True}

    # Revoking UserSession flips active -> False immediately.
    session.is_revoked = True
    session.revoked_at = timezone.now()
    session.revoked_reason = "LOGOUT"
    session.save(update_fields=("is_revoked", "revoked_at", "revoked_reason"))

    revoked = APIClient().post(
        route,
        {},
        format="json",
        HTTP_X_SERVICE_KEY=ai_key,
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"] == {"active": False}


def test_team_ai_authorize_and_project_context_contracts(settings):
    settings.WORK_SERVICE_KEYS = {"ai": [WORK_AI_KEY], "integration": [WORK_INTEGRATION_KEY]}
    settings.INTEGRATION_WORK_SERVICE_KEYS = []
    settings.WORK_INTEGRATION_SERVICE_KEY = ""

    leader = _create_user()
    outsider = _create_user()
    project, _, _ = _create_project_with_member(leader)
    leader_access, _, _ = _login(leader)
    outsider_access, _, _ = _login(outsider)

    auth_route = f"/api/v1/internal/ai/targets/project/{project.pk}/authorize"
    context_route = f"/api/v1/internal/ai/targets/project/{project.pk}/contexts/project"

    # Authorize enforces Bearer + AI X-Service-Key.
    no_bearer = APIClient().post(
        auth_route,
        {"action": "ai.analyze", "intent": "backlog_generation"},
        format="json",
        HTTP_X_SERVICE_KEY=WORK_AI_KEY,
    )
    assert no_bearer.status_code == 401
    assert no_bearer.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    wrong_service_key = APIClient().post(
        auth_route,
        {"action": "ai.analyze", "intent": "backlog_generation"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {leader_access}",
        HTTP_X_SERVICE_KEY=WORK_INTEGRATION_KEY,
    )
    assert wrong_service_key.status_code == 403

    authorized = APIClient().post(
        auth_route,
        {"action": "ai.analyze", "intent": "backlog_generation"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {leader_access}",
        HTTP_X_SERVICE_KEY=WORK_AI_KEY,
    )
    assert authorized.status_code == 200
    assert authorized.headers["Cache-Control"] == "no-store"
    auth_body = authorized.json()
    assert set(auth_body) == ENVELOPE_KEYS
    assert auth_body["data"] == {
        "target_type": "project",
        "target_id": str(project.pk),
        "action": "ai.analyze",
        "allowed": True,
    }

    # Outsider cannot authorize or read context.
    outsider_resp = APIClient().post(
        auth_route,
        {"action": "ai.analyze", "intent": "backlog_generation"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {outsider_access}",
        HTTP_X_SERVICE_KEY=WORK_AI_KEY,
    )
    assert outsider_resp.status_code == 404

    # Context endpoint returns raw non-envelope JSON with Cache-Control: no-store.
    ctx_resp = APIClient().get(
        context_route,
        HTTP_AUTHORIZATION=f"Bearer {leader_access}",
        HTTP_X_SERVICE_KEY=WORK_AI_KEY,
    )
    assert ctx_resp.status_code == 200
    assert ctx_resp.headers["Cache-Control"] == "no-store"
    ctx_body = ctx_resp.json()
    assert "success" not in ctx_body
    assert set(ctx_body) == {"domain", "as_of", "status", "source_version", "data", "warning"}
    assert ctx_body["domain"] == "project"
    assert ctx_body["status"] == "available"
    assert ctx_body["data"]["id"] == str(project.pk)
    assert len(ctx_body["data"]["tasks"]) == 1


# ---------------------------------------------------------------------------
# Team Integration Contracts
# ---------------------------------------------------------------------------


def test_team_integration_root_users_me_returns_current_user_envelope():
    user = _create_user()
    access, _, _ = _login(user)

    assert APIClient().get("/users/me").status_code == 401

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = client.get("/users/me")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["success"] is True
    assert body["data"]["id"] == str(user.pk)
    assert body["data"]["email"] == user.email


def test_team_integration_github_oauth_mapping_lookup_and_service_key(settings):
    user = _create_user()
    integration_key = settings.IDENTITY_SERVICE_KEYS["integration"]
    ai_key = settings.IDENTITY_SERVICE_KEYS["ai"]
    route = f"/api/v1/internal/users/{user.pk}/oauth/GITHUB"

    # Rejects missing key and wrong caller key (e.g. AI key).
    assert APIClient().get(route).status_code == 403
    assert APIClient().get(route, HTTP_X_SERVICE_KEY=ai_key).status_code == 403

    # Returns mapping=None before linking.
    unlinked = APIClient().get(route, HTTP_X_SERVICE_KEY=integration_key)
    assert unlinked.status_code == 200
    assert unlinked.json()["data"] == {"user_id": str(user.pk), "mapping": None}

    # Returns provider_user_id and github_username once linked.
    SocialAccount.objects.create(
        user=user,
        provider="github",
        uid="987654",
        extra_data={"login": "utask-octocat"},
    )
    user.profile.github_username = "utask-octocat"
    user.profile.save(update_fields=("github_username", "updated_at"))

    linked = APIClient().get(route, HTTP_X_SERVICE_KEY=integration_key)
    assert linked.status_code == 200
    assert linked.json()["data"] == {
        "user_id": str(user.pk),
        "mapping": {"provider_user_id": "987654", "github_username": "utask-octocat"},
    }

    # Endpoint is read-only per contracts/api/identity-service.yaml (PUT/DELETE -> 405).
    put_resp = APIClient().put(route, {}, format="json", HTTP_X_SERVICE_KEY=integration_key)
    del_resp = APIClient().delete(route, HTTP_X_SERVICE_KEY=integration_key)
    assert put_resp.status_code == 405
    assert del_resp.status_code == 405


def test_team_integration_project_authorize_and_operation_receipt_contracts(settings):
    settings.WORK_SERVICE_KEYS = {"ai": [WORK_AI_KEY], "integration": [WORK_INTEGRATION_KEY]}
    settings.INTEGRATION_WORK_SERVICE_KEYS = []
    settings.WORK_INTEGRATION_SERVICE_KEY = ""

    leader = _create_user()
    project, _, _ = _create_project_with_member(leader)
    leader_access, _, _ = _login(leader)

    auth_route = f"/api/v1/internal/integration/projects/{project.pk}/authorize"
    assert (
        APIClient()
        .post(
            auth_route,
            {"action": "github.read"},
            format="json",
            HTTP_X_SERVICE_KEY=WORK_INTEGRATION_KEY,
        )
        .status_code
        == 401
    )
    assert (
        APIClient()
        .post(
            auth_route,
            {"action": "github.read"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {leader_access}",
            HTTP_X_SERVICE_KEY=WORK_AI_KEY,
        )
        .status_code
        == 403
    )

    authorized = APIClient().post(
        auth_route,
        {"action": "github.read"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {leader_access}",
        HTTP_X_SERVICE_KEY=WORK_INTEGRATION_KEY,
    )
    assert authorized.status_code == 200
    assert authorized.headers["Cache-Control"] == "no-store"
    assert authorized.json()["data"] == {
        "project_id": str(project.pk),
        "action": "github.read",
        "allowed": True,
    }

    # Operation receipt endpoint enforces X-Service-Key and returns no-store envelope.
    op_id = "op-contract-1"
    receipt_route = f"/api/v1/internal/integration/projects/{project.pk}/github/operations/{op_id}"
    assert APIClient().get(receipt_route).status_code == 403
    assert (
        APIClient().get(receipt_route, HTTP_X_SERVICE_KEY=WORK_INTEGRATION_KEY).status_code == 404
    )

    GitHubConnectionOperation.objects.create(
        project=project,
        operation_id=op_id,
        actor_user_id=leader.pk,
        action="CONNECT",
        payload_hash="a" * 64,
        request_body={
            "operation_id": op_id,
            "action": "CONNECT",
            "expected_generation": 0,
            "github_repo_id": "12345",
        },
        state="CONFIRM",
        generation=1,
        prepared={"repo_id": "12345", "source_version": 1},
        accepted_at=timezone.now(),
    )

    receipt = APIClient().get(receipt_route, HTTP_X_SERVICE_KEY=WORK_INTEGRATION_KEY)
    assert receipt.status_code == 200
    assert receipt.headers["Cache-Control"] == "no-store"
    receipt_body = receipt.json()
    assert set(receipt_body) == ENVELOPE_KEYS
    assert receipt_body["success"] is True
    assert receipt_body["data"] == {
        "applied": True,
        "project_id": str(project.pk),
        "operation_id": op_id,
        "generation": 1,
        "status": "PENDING",
        "repo_id": "12345",
        "source_version": 1,
    }


# ---------------------------------------------------------------------------
# Team Notification Contracts
# ---------------------------------------------------------------------------


def test_team_notification_contacts_enforces_token_and_returns_raw_json(settings):
    token = settings.NOTIFICATION_SERVICE_TOKEN
    route = "/api/v1/internal/users/notification-contacts"
    active = _create_user(first_name="Lan", last_name="Trần")
    deleted = _create_user(deleted_at=timezone.now())

    assert APIClient().post(route, {"user_ids": [str(active.pk)]}, format="json").status_code == 403
    assert (
        APIClient()
        .post(
            route,
            {"user_ids": [str(active.pk)]},
            format="json",
            HTTP_X_SERVICE_TOKEN="wrong-token",
        )
        .status_code
        == 403
    )

    response = APIClient().post(
        route,
        {"user_ids": [str(active.pk), str(deleted.pk), str(uuid4())]},
        format="json",
        HTTP_X_SERVICE_TOKEN=token,
    )
    assert response.status_code == 200
    body = response.json()
    assert "success" not in body
    assert set(body) == {"users"}
    assert body["users"] == [
        {
            "user_id": str(active.pk),
            "email": active.email,
            "display_name": "Trần Lan",
            "account_status": AccountStatus.ACTIVE,
        }
    ]


def test_team_notification_contacts_sets_cache_control_no_store(settings):
    user = _create_user()
    response = APIClient().post(
        "/api/v1/internal/users/notification-contacts",
        {"user_ids": [str(user.pk)]},
        format="json",
        HTTP_X_SERVICE_TOKEN=settings.NOTIFICATION_SERVICE_TOKEN,
    )
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-store"


def test_team_notification_resolve_enforces_token_and_returns_raw_no_store_json(settings):
    token = settings.NOTIFICATION_SERVICE_TOKEN
    route = "/api/v1/internal/notifications/resolve"
    leader = _create_user()
    member = _create_user()
    outsider = _create_user()
    project, _, task = _create_project_with_member(leader, member)
    TaskAssignment.objects.create(task=task, user_id=member.pk)

    single_payload = {
        "user_id": str(member.pk),
        "event_type": "task.assigned",
        "project_id": str(project.pk),
        "data": {"task_id": str(task.pk), "actor_user_id": str(leader.pk)},
    }
    assert APIClient().post(route, single_payload, format="json").status_code == 403
    assert (
        APIClient()
        .post(route, single_payload, format="json", HTTP_X_SERVICE_TOKEN="wrong")
        .status_code
        == 403
    )

    # Single resolution: eligible member gets raw non-envelope JSON + Cache-Control: no-store.
    resp = APIClient().post(
        route,
        single_payload,
        format="json",
        HTTP_X_SERVICE_TOKEN=token,
    )
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.json()
    assert "success" not in body
    assert body["eligible"] is True
    assert body["title"] == "Bạn được giao công việc"
    assert body["target"] == {
        "kind": "board-issue",
        "projectId": str(project.pk),
        "issueKey": f"{project.identifier}-{task.sequence_id}",
    }

    # Batch resolution: outsider is denied (eligible=False).
    batch_resp = APIClient().post(
        route,
        {
            "items": [
                single_payload,
                {
                    "user_id": str(outsider.pk),
                    "event_type": "task.assigned",
                    "project_id": str(project.pk),
                    "data": {"task_id": str(task.pk), "actor_user_id": str(leader.pk)},
                },
            ]
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=token,
    )
    assert batch_resp.status_code == 200
    assert batch_resp.headers["Cache-Control"] == "no-store"
    batch_body = batch_resp.json()
    assert "success" not in batch_body
    assert [row["eligible"] for row in batch_body["results"]] == [True, False]


def test_team_notification_outbox_topics_and_producers_for_identity_and_work():
    # 1. Identity outbox row via real PATCH /api/auth/users/me
    leader = _create_user()
    leader_access, _, _ = _login(leader)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {leader_access}")

    identity_resp = client.patch(
        "/api/auth/users/me",
        {"bio": "Contract outbox check"},
        format="json",
        secure=True,
    )
    assert identity_resp.status_code == 200

    identity_event = (
        OutboxEvent.objects.filter(
            aggregate_id=str(leader.pk),
            event_type="identity.user.updated",
        )
        .order_by("-created_at")
        .first()
    )
    assert identity_event is not None
    assert identity_event.topic == "utask.identity.events"
    assert identity_event.producer == "identity-service"
    assert identity_event.data["producer"] == "identity-service"

    # 2. Work outbox row via real PATCH /api/work/projects/<id>/
    project, _, _ = _create_project_with_member(leader)
    work_resp = client.patch(
        f"/api/work/projects/{project.pk}/",
        {"expected_version": project.version, "name": "Renamed Contract Project"},
        format="json",
    )
    assert work_resp.status_code == 200

    work_event = (
        OutboxEvent.objects.filter(
            partition_key=str(project.pk),
            event_type="project.updated",
        )
        .order_by("-created_at")
        .first()
    )
    assert work_event is not None
    assert work_event.topic == "utask.work.events"
    assert work_event.producer == "work-service"
    assert work_event.data["producer"] == "work-service"
    assert work_event.stream_sequence >= 1


def test_shared_infrastructure_adapter_fakes_match_runtime_contracts(settings):
    from types import SimpleNamespace

    from infrastructure.ai import ai_client
    from infrastructure.integration import integration_client
    from infrastructure.storage import storage_client
    from tests.fixtures.ai_proposals import FakeAIProposals, backlog_payload
    from tests.fixtures.integration import FakeIntegration
    from tests.fixtures.storage import InMemoryStorage

    settings.CORE_STORAGE_ADAPTER = "tests.fixtures.storage.InMemoryStorage"
    settings.WORK_STORAGE_ADAPTER = "tests.fixtures.storage.InMemoryStorage"
    settings.WORK_AI_ADAPTER = "tests.fixtures.ai_proposals.FakeAIProposals"
    settings.INTEGRATION_ADAPTER = "tests.fixtures.integration.FakeIntegration"

    InMemoryStorage.reset()
    FakeAIProposals.reset()
    FakeIntegration.reset()

    # 1. Storage adapter (attachment + avatar operations)
    st = storage_client()
    fake_attachment = SimpleNamespace(
        pk=uuid4(),
        storage_key="work/proj/file1",
        content_type="text/plain",
        file_size=12,
    )
    put_url, headers = st.presign(fake_attachment)
    assert put_url.startswith("https://storage.test/put/")
    assert headers["If-None-Match"] == "*"
    facts = st.inspect(fake_attachment)
    assert facts.size == 12 and facts.valid_content is True
    assert st.download(fake_attachment).startswith("https://storage.test/get/")
    st.delete(fake_attachment.storage_key)
    assert fake_attachment.storage_key in InMemoryStorage.deletes

    avatar_key = f"avatars/{uuid4()}/1_abc.png"
    assert st.presign_avatar(avatar_key, "image/png", 2048).endswith(avatar_key)
    InMemoryStorage.put_avatar(avatar_key, content_type="image/png", content_length=2048)
    assert st.head_avatar(avatar_key) == {"ContentType": "image/png", "ContentLength": 2048}
    assert st.delete_avatar(avatar_key) is True
    assert st.delete_avatar(avatar_key) is False

    # 2. AI proposals adapter
    leader = _create_user()
    project, _, _ = _create_project_with_member(leader)
    FakeAIProposals.register(project.pk, actor_ids=[leader.pk])
    proof = ai_client().verify(
        actor=leader,
        project_id=project.pk,
        proposal_id="proposal-1",
        kind="BACKLOG",
        bearer="dummy-token",
    )
    assert proof.validate(leader, project.pk, backlog_payload(project), "BACKLOG") == proof

    # 3. Integration adapter
    integ = integration_client()
    prep = integ.prepare(
        project_id=project.pk,
        body={
            "operation_id": "op-fake-1",
            "action": "CONNECT",
            "expected_generation": 0,
            "github_repo_id": "12345",
        },
        bearer="dummy-token",
    )
    prep.validate()
    assert prep.status == "PENDING"
    status_doc = integ.status(project_id=project.pk, operation_id="op-fake-1")
    assert status_doc["state"] == "PREPARED"
    confirmed = integ.confirm(project_id=project.pk, operation_id="op-fake-1", generation=1)
    confirmed.validate()
    assert confirmed.status == "CONNECTED"
    ref = integ.verify_reference(
        project_id=project.pk,
        repo_id="12345",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="42",
        bearer="dummy-token",
        actor=leader,
    )
    ref.validate()
    activity = integ.fetch_project_activity(project_id=project.pk, bearer="dummy-token")
    assert activity["project_id"] == str(project.pk)
