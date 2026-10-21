import json
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from notifications import clients
from notifications.authentication import NotificationAuthentication
from notifications.models import EmailDelivery, Inbox, Quarantine
from notifications.services import IDENTITY_EVENTS, WORK_EVENTS, persist
from tests.test_service import email_row, encrypted_mail, event

pytestmark = pytest.mark.django_db


def test_bundled_contracts_match_canonical():
    root = Path(__file__).resolve().parents[3]
    for name in IDENTITY_EVENTS | WORK_EVENTS.keys():
        bundled = (
            Path(__file__).resolve().parents[1] / "notifications" / "schemas" / (name + ".v1.json")
        )
        assert json.loads(bundled.read_text()) == json.loads(
            (root / "contracts/events" / (name + ".v1.json")).read_text()
        )


@pytest.mark.parametrize(
    "change",
    [
        {"event_version": True},
        {"occurred_at": "bad"},
        {"trace_id": "invalid"},
        {"data": {"recipient_ids": []}},
        {"producer": "identity-service"},
    ],
)
def test_invalid_contract_quarantined(change):
    assert persist("work", {**event(), **change}) is None
    assert not Inbox.objects.exists()
    assert Quarantine.objects.get().reason == "invalid_envelope"


def test_plaintext_secret_cannot_enter_database():
    payload = encrypted_mail()
    payload["data"]["secret"] = {"token": "do-not-persist"}
    assert persist("identity", payload) is None
    assert not Inbox.objects.exists()
    assert "do-not-persist" not in str(Quarantine.objects.values().get())


def test_auth_checks_signature_algorithm_session_and_revocation():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    claims = {
        "sub": str(uuid4()),
        "exp": int(timezone.now().timestamp()) + 120,
        "iss": settings.IDENTITY_JWT_ISSUER,
        "aud": settings.IDENTITY_JWT_AUDIENCE,
        "token_type": "access",
    }
    token = jwt.encode(claims, key, algorithm="RS256")
    factory = APIRequestFactory()
    auth = NotificationAuthentication()
    assert auth.authenticate(factory.get("/")) is None
    with patch("notifications.authentication.IdentityClient") as client:
        client.return_value.jwks.return_value = {"keys": [jwk]}
        client.return_value.session_active.return_value = True
        actor, _ = auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Bearer " + token))
        assert str(actor.id) == claims["sub"]
        client.return_value.session_active.return_value = False
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Bearer " + token))
        client.return_value.reset_mock()
        bad = jwt.encode(claims, "test-hmac-key-with-at-least-32-bytes", algorithm="HS256")
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Bearer " + bad))
        client.return_value.jwks.assert_not_called()
    with pytest.raises(AuthenticationFailed):
        auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Basic abc"))


@pytest.mark.parametrize("body", [{}, {"keys": [1]}, {"keys": None}])
def test_identity_jwks_fail_closed(body):
    with (
        patch("notifications.clients.request_json", return_value=body),
        pytest.raises(clients.DependencyUnavailable),
    ):
        clients.IdentityClient().jwks()


@override_settings(IDENTITY_NOTIFICATION_SERVICE_KEY="test-key")
def test_session_contract():
    with patch(
        "notifications.clients.request_json",
        return_value={"success": True, "data": {"active": True}},
    ):
        assert clients.IdentityClient().session_active("t")
    with (
        patch("notifications.clients.request_json", return_value={"active": True}),
        pytest.raises(clients.DependencyUnavailable),
    ):
        clients.IdentityClient().session_active("t")


@override_settings(NOTIFICATION_SERVICE_TOKEN="test-token")
def test_contact_and_batch_resolve_contracts():
    user_id = uuid4()
    user = {
        "user_id": str(user_id),
        "email": "me@example.com",
        "account_status": "ACTIVE",
        "display_name": "Me",
    }
    with patch("notifications.clients.request_json", return_value={"users": [user]}):
        assert clients.contact(user_id) == user
    with patch("notifications.clients.request_json", return_value={"users": []}):
        assert clients.contact(user_id) is None
    row = Mock(inbox=Mock(envelope=event()))
    with patch(
        "notifications.clients.request_json",
        side_effect=lambda *a, **kw: {"results": [{"eligible": False}] * len(kw["json"]["items"])},
    ) as request:
        assert clients.resolve_many([row] * 201, user_id) == [None] * 201
        assert request.call_count == 3
    with patch(
        "notifications.clients.request_json",
        return_value={
            "eligible": True,
            "title": "T",
            "body": "B",
            "target": {"kind": "backlog", "projectId": "p"},
        },
    ):
        assert clients.resolve(row.inbox, user_id)["title"] == "T"
    with (
        patch("notifications.clients.request_json", return_value={"results": []}),
        pytest.raises(clients.DependencyUnavailable),
    ):
        clients.resolve_many([row], user_id)
    assert not clients.valid_target({"kind": [], "projectId": "p"})
    assert not clients.valid_target(
        {"kind": "backlog", "projectId": "p", "url": "https://evil.test"}
    )


@pytest.mark.parametrize(
    "response",
    [Mock(status_code=302), Mock(status_code=503), Mock(status_code=200, json=lambda: [])],
)
def test_http_rejects_redirects_and_malformed_responses(response):
    with (
        patch("notifications.clients.requests.request", return_value=response),
        pytest.raises(clients.DependencyUnavailable),
    ):
        clients.request_json("GET", "http://dependency.test")


def test_http_success_and_connection_failure():
    response = Mock(status_code=200, json=lambda: {"ok": True})
    with patch("notifications.clients.requests.request", return_value=response) as request:
        assert clients.request_json("GET", "http://dependency.test") == {"ok": True}
        assert request.call_args.kwargs["allow_redirects"] is False
    with (
        patch("notifications.clients.requests.request", side_effect=requests.Timeout),
        pytest.raises(clients.DependencyUnavailable),
    ):
        clients.request_json("GET", "http://dependency.test")


def test_replay_requires_explicit_unknown_confirmation():
    row = email_row()
    EmailDelivery.objects.filter(pk=row.pk).update(status="delivery_unknown")
    with pytest.raises(CommandError):
        call_command("replay_notifications", str(row.pk), email=True)
    call_command("replay_notifications", str(row.pk), email=True, confirm_unknown=True)
    row.refresh_from_db()
    assert row.status == "pending" and row.attempts == 0
    with pytest.raises(CommandError):
        call_command("replay_notifications", str(row.pk), email=True)
    Inbox.objects.filter(pk=row.inbox_id).update(status="failed", attempts=5)
    call_command("replay_notifications", str(row.inbox_id))
    row.inbox.refresh_from_db()
    assert row.inbox.status == "pending"


@override_settings(NOTIFICATION_IDENTITY_ENABLED=True)
def test_consumer_persists_before_manual_commit_and_closes():
    message = Mock()
    message.error.return_value = None
    message.value.return_value = json.dumps(encrypted_mail()).encode()
    consumer = Mock()
    consumer.poll.side_effect = [message, KeyboardInterrupt()]

    def committed(**kwargs):
        assert Inbox.objects.count() == 1
        assert kwargs["asynchronous"] is False

    consumer.commit.side_effect = committed
    with patch("confluent_kafka.Consumer", return_value=consumer), pytest.raises(KeyboardInterrupt):
        call_command("consume_notifications", source="identity")
    consumer.close.assert_called_once()


@override_settings(NOTIFICATION_IDENTITY_ENABLED=True)
def test_consumer_does_not_commit_when_database_fails():
    message = Mock()
    message.error.return_value = None
    message.value.return_value = json.dumps(encrypted_mail()).encode()
    consumer = Mock()
    consumer.poll.return_value = message
    with (
        patch("confluent_kafka.Consumer", return_value=consumer),
        patch(
            "notifications.management.commands.consume_notifications.persist",
            side_effect=RuntimeError("db"),
        ),
        pytest.raises(RuntimeError),
    ):
        call_command("consume_notifications", source="identity")
    consumer.commit.assert_not_called()
    consumer.close.assert_called_once()


def test_failed_payload_cleanup_keeps_dedupe_and_blocks_replay():
    from datetime import timedelta

    from notifications.tasks import cleanup

    payload = event()
    row = persist("work", payload)
    Inbox.objects.filter(pk=row.pk).update(
        status="failed", created_at=timezone.now() - timedelta(days=8)
    )
    cleanup()
    row.refresh_from_db()
    assert row.envelope == {"redacted": True}
    assert persist("work", payload).pk == row.pk
    with pytest.raises(CommandError, match="retention"):
        call_command("replay_notifications", str(row.pk))


def test_redacted_identity_replay_requires_new_event():
    row = email_row()
    row.inbox.envelope["data"]["secret"] = None
    row.inbox.save()
    EmailDelivery.objects.filter(pk=row.pk).update(status="failed")
    with pytest.raises(CommandError, match="reissue"):
        call_command("replay_notifications", str(row.pk), email=True)


def test_inbox_multi_recipient_failure_rolls_back_earlier_recipient():
    from notifications.models import Notification
    from notifications.services import process_inbox

    payload = event(recipient_ids=[str(uuid4()), str(uuid4())])
    row = persist("work", payload)
    with patch(
        "notifications.clients.resolve",
        side_effect=[{"title": "T", "body": "B", "target": None}, clients.DependencyUnavailable()],
    ):
        process_inbox(row.pk)
    assert not Notification.objects.exists()
    assert not EmailDelivery.objects.exists()
    row.refresh_from_db()
    assert row.status == "pending" and row.attempts == 1


def test_failed_redacted_inbox_never_enters_feed_or_unread_count():
    from datetime import timedelta

    from rest_framework.test import APIClient

    from notifications.authentication import Actor
    from notifications.models import Notification
    from notifications.tasks import cleanup

    row = persist("work", event())
    user_id = uuid4()
    Notification.objects.create(inbox=row, user_id=user_id)
    Inbox.objects.filter(pk=row.pk).update(
        status="failed", created_at=timezone.now() - timedelta(days=8)
    )
    cleanup()
    client = APIClient()
    client.force_authenticate(Actor(user_id))
    with patch("notifications.clients.resolve_many", return_value=[]) as resolve_many:
        assert client.get("/").data["count"] == 0
        assert client.get("/unread-count").data["count"] == 0
    assert all(call.args[0] == [] for call in resolve_many.call_args_list)
