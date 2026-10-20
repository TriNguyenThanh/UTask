"""Local HTTP E2E: real Integration API, database and adapters, fake peer services."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import requests
from cryptography.fernet import Fernet
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker

from apps.github_accounts.consent import lock_generation
from apps.github_accounts.credentials import store_credential
from apps.github_accounts.models import GitHubAccount, GitHubCredential
from apps.github_connections.models import ConnectionOperation, IntegrationOutboxEvent
from apps.github_connections.publisher import TOPIC, publish_outbox
from tests.contract.test_github_app_contract import validate
from tests.factories import token_identity

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]
WORK_KEY = "w" * 32
AI_KEY = "ai-" + "b" * 32
CALLBACK_KEY = "c" * 32
SHA = "a" * 40
DATE = "2026-10-20T00:00:00Z"


class PeerServer:
    """Reusable threaded stub supporting nested Integration-to-Work callbacks."""

    def __init__(self, dispatch):
        self.failures = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                close_old_connections()
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length)) if length else None
                    status, payload = dispatch(self.command, self.path, self.headers, body)
                except Exception as error:
                    owner.failures.append(type(error).__name__)
                    status, payload = 500, {"error": "stub assertion failed"}
                finally:
                    close_old_connections()
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive()
        assert not self.failures


@pytest.fixture
def wire(settings, request):
    # This API-only service has no static URL; Django's test server requires one.
    settings.STATIC_URL = "/static/"
    settings.MEDIA_URL = "/media/"
    live_server = request.getfixturevalue("live_server")
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_AI_CONTEXT_ENABLED = True
    settings.INTEGRATION_KAFKA_ENABLED = True
    settings.INTEGRATION_KAFKA = {"bootstrap.servers": "fake-broker:9092"}
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ID = "42"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "fixture-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    settings.INTEGRATION_CONSENT_KEY = Fernet.generate_key().decode()
    settings.INTEGRATION_CREDENTIAL_KEYS = [Fernet.generate_key().decode()]
    settings.INTEGRATION_SERVICE_KEYS = {"work": WORK_KEY, "ai": AI_KEY}
    settings.INTEGRATION_WORK_SERVICE_KEY = CALLBACK_KEY
    connector, reader, project = uuid4(), uuid4(), uuid4()
    with transaction.atomic():
        lock_generation(connector)
        GitHubAccount.objects.create(
            user_id=connector,
            github_user_id="123",
            github_username="Octo",
            verified_at=timezone.now(),
        )
        store_credential(user_id=connector, identity=token_identity(access_token="connector-token"))
    state = SimpleNamespace(
        project=project,
        connector=connector,
        reader=reader,
        receipt=None,
        identity_calls=[],
        github_calls=[],
        receipt_calls=0,
        authorize_calls=0,
        allowed=True,
        integration_url=live_server.url,
    )
    project_path = f"/api/v1/internal/projects/{project}/github"

    def dispatch(method, raw_path, headers, body):
        path = urlsplit(raw_path).path
        if path == "/identity/users/me":
            token = headers.get("Authorization")
            assert token in {"Bearer connector-bearer", "Bearer reader-bearer"}
            assert headers.get("X-Service-Key") is None
            state.identity_calls.append(token)
            actor = connector if token == "Bearer connector-bearer" else reader
            return 200, {"success": True, "data": {"id": str(actor)}}
        if path == "/driver/connect":
            # Work is a separate HTTP peer driving Integration's real API.
            prepared = requests.post(
                live_server.url + project_path + "/connection/prepare",
                json={
                    "operation_id": "wire-connect",
                    "action": "CONNECT",
                    "expected_generation": 0,
                    "github_repo_id": "12",
                },
                headers={"X-Service-Key": WORK_KEY, "Authorization": "Bearer connector-bearer"},
                timeout=10,
            )
            assert prepared.status_code == 200
            fact = prepared.json()["data"]
            validate("ConnectionFact", fact)
            state.receipt = {
                name: fact[name]
                for name in (
                    "project_id",
                    "operation_id",
                    "generation",
                    "status",
                    "repo_id",
                    "source_version",
                )
            } | {"applied": True}
            confirmed = requests.post(
                live_server.url + project_path + "/connection/confirm",
                json={"operation_id": "wire-connect", "generation": fact["generation"]},
                headers={"X-Service-Key": WORK_KEY},
                timeout=10,
            )
            return confirmed.status_code, confirmed.json()
        if path.endswith("/github/operations/wire-connect"):
            assert method == "GET"
            assert headers.get("X-Service-Key") == CALLBACK_KEY
            assert headers.get("Authorization") is None
            state.receipt_calls += 1
            return 200, {"success": True, "data": state.receipt}
        if path.endswith("/authorize"):
            assert method == "POST"
            assert headers.get("X-Service-Key") == CALLBACK_KEY
            assert headers.get("Authorization") == "Bearer reader-bearer"
            assert body == {"action": "github.read"}
            state.authorize_calls += 1
            return 200, {
                "success": True,
                "data": {
                    "project_id": str(project),
                    "action": "github.read",
                    "allowed": state.allowed,
                },
            }
        assert path.startswith("/github/")
        assert headers.get("Authorization") == "Bearer connector-token"
        assert headers.get("X-Service-Key") is None
        assert method == "GET"
        state.github_calls.append(path)
        path = path.removeprefix("/github/")
        if path == "user/installations":
            return 200, {
                "total_count": 1,
                "installations": [
                    {
                        "id": 55,
                        "app_id": 42,
                        "account": {"id": 123, "login": "Octo", "type": "User"},
                        "repository_selection": "selected",
                        "suspended_at": None,
                    }
                ],
            }
        if path == "user/installations/55/repositories":
            return 200, {
                "total_count": 1,
                "repositories": [
                    {
                        "id": 12,
                        "name": "demo",
                        "full_name": "octo/demo",
                        "private": True,
                    }
                ],
            }
        if path == "repositories/12":
            return 200, {
                "id": 12,
                "name": "demo",
                "owner": {"login": "octo"},
                "default_branch": "main",
                "provider_secret": "discard",
            }
        if path == "repos/octo/demo/commits":
            return 200, [
                {
                    "sha": SHA,
                    "commit": {"message": "Fix bug\nprivate body", "committer": {"date": DATE}},
                    "html_url": f"https://github.com/octo/demo/commit/{SHA}",
                }
            ]
        if path == "repos/octo/demo/pulls":
            return 200, [
                {
                    "number": 3,
                    "title": "Fix bug",
                    "state": "open",
                    "html_url": "https://github.com/octo/demo/pull/3",
                    "updated_at": DATE,
                }
            ]
        if path == "repos/octo/demo/issues":
            return 200, [
                {
                    "number": 4,
                    "title": "Next bug",
                    "state": "open",
                    "html_url": "https://github.com/octo/demo/issues/4",
                    "updated_at": DATE,
                }
            ]
        raise AssertionError("Unexpected peer route")

    with PeerServer(dispatch) as peers:
        settings.INTEGRATION_IDENTITY_URL = peers.url + "/identity"
        settings.INTEGRATION_WORK_URL = peers.url
        original = requests.request

        def loopback_github(method, url, **kwargs):
            assert not connection.in_atomic_block
            if url.startswith("https://api.github.com/"):
                url = peers.url + "/github/" + url.removeprefix("https://api.github.com/")
            else:
                assert url.startswith(peers.url)
            return original(method, url, **kwargs)

        with patch("requests.request", side_effect=loopback_github):
            state.peers = peers
            yield state


class MemoryBroker:
    def __init__(self):
        self.messages = []

    def factory(self, config):
        assert config["enable.idempotence"] is True
        return self

    def produce(self, topic, key, value, on_delivery):
        assert not connection.in_atomic_block
        self.messages.append((topic, key, json.loads(value)))
        on_delivery(None, None)

    def flush(self, timeout):
        return 0


def test_work_connect_receipt_event_and_ai_context_over_local_http(wire):
    base = f"{wire.integration_url}/api/v1/internal/projects/{wire.project}/github"
    # A wrong key never sends the actor's Bearer to Identity.
    denied = requests.post(
        base + "/connection/prepare",
        json={},
        headers={"X-Service-Key": AI_KEY, "Authorization": "Bearer connector-bearer"},
        timeout=10,
    )
    assert denied.status_code == 403
    assert not wire.identity_calls
    assert not wire.github_calls

    connected = requests.post(wire.peers.url + "/driver/connect", json={}, timeout=20)
    assert connected.status_code == 200, connected.text
    validate("ConnectionFact", connected.json()["data"])
    assert connected.json()["data"]["status"] == "CONNECTED"
    assert wire.receipt_calls == 1
    assert wire.identity_calls == ["Bearer connector-bearer"]
    assert ConnectionOperation.objects.get().state == "CONFIRMED"
    assert IntegrationOutboxEvent.objects.get().state == "PENDING"

    broker = MemoryBroker()
    assert publish_outbox(producer_factory=broker.factory) == 1
    assert len(broker.messages) == 1
    topic, key, envelope = broker.messages[0]
    assert topic == TOPIC
    assert key == str(wire.project).encode()
    schema = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "contracts/events/integration.project.connection.changed.v1.json"
        ).read_text()
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(envelope)
    assert envelope["payload"] == connected.json()["data"]
    assert IntegrationOutboxEvent.objects.get().state == "PUBLISHED"

    before = len(wire.github_calls)
    wire.allowed = False
    denied_context = requests.get(
        base + "/context",
        headers={"X-Service-Key": AI_KEY, "Authorization": "Bearer reader-bearer"},
        timeout=10,
    )
    assert denied_context.status_code == 403
    assert len(wire.github_calls) == before

    wire.allowed = True
    context = requests.get(
        base + "/context",
        headers={"X-Service-Key": AI_KEY, "Authorization": "Bearer reader-bearer"},
        timeout=10,
    )
    assert context.status_code == 200, context.text
    document = context.json()
    validate("GitHubContextDocument", document)
    assert "success" not in document
    assert document["status"] == "available"
    assert document["data"]["mapping_status"] == "CONNECTED"
    assert all(len(document["data"][name]) == 1 for name in ("commits", "pull_requests", "issues"))
    assert document["data"]["commits"][0]["title"] == "Fix bug"
    assert wire.authorize_calls == 2
    assert not GitHubCredential.objects.filter(user_id=wire.reader).exists()
    serialized = json.dumps([connected.json(), document, envelope])
    assert all(
        secret not in serialized
        for secret in (
            WORK_KEY,
            AI_KEY,
            CALLBACK_KEY,
            "connector-token",
            "provider_secret",
            "private body",
        )
    )
    assert not wire.peers.failures
