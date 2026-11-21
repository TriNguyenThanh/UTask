import base64
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from notifications import clients
from notifications.authentication import Actor
from notifications.mail import PermanentFailure, UnknownDelivery, identity_content, send
from notifications.models import (
    DailyQuota,
    EmailDelivery,
    Inbox,
    Notification,
    Preference,
    Quarantine,
)
from notifications.services import persist, process_inbox
from notifications.tasks import claim, cleanup, deliver, dispatch
from tests.fixtures.events import email_row, encrypted_mail, event

pytestmark = pytest.mark.django_db


def test_inbox_dedupe_collision_and_invalid():
    payload = event()
    first = persist("work", payload)
    assert persist("work", payload).pk == first.pk
    changed = {**payload, "data": {**payload["data"], "recipient_ids": []}}
    persist("work", changed)
    assert Inbox.objects.count() == 1
    assert Quarantine.objects.get().reason == "event_id_collision"
    persist("work", {"event_id": "bad"})
    assert Quarantine.objects.count() == 2
    assert persist("identity", event("identity", "identity.user.created")) is None


def test_work_process_retries_and_atomic_replay():
    row = persist("work", event())
    with patch("notifications.clients.resolve", side_effect=clients.DependencyUnavailable):
        process_inbox(row.pk)
    row.refresh_from_db()
    assert row.attempts == 1 and row.status == "pending"
    row.next_attempt = timezone.now()
    row.save()
    with patch(
        "notifications.clients.resolve",
        return_value={"title": "Task", "body": "Body", "target": None},
    ):
        process_inbox(row.pk)
        process_inbox(row.pk)
    assert Notification.objects.count() == EmailDelivery.objects.count() == 1


def test_preferences_and_transition_no_email():
    payload = event(event_type="task.transitioned")
    row = persist("work", payload)
    with patch(
        "notifications.clients.resolve", return_value={"title": "T", "body": "B", "target": None}
    ):
        process_inbox(row.pk)
    assert Notification.objects.count() == 1
    assert not EmailDelivery.objects.exists()


def test_api_owner_scope_preferences_and_fail_closed():
    row = persist("work", event())
    row.status = "processed"
    row.save()
    owner = uuid4()
    n = Notification.objects.create(inbox=row, user_id=owner)
    client = APIClient()
    assert client.get("/").status_code == 401
    client.force_authenticate(Actor(owner))
    with patch(
        "notifications.clients.resolve_many",
        return_value=[{"title": "T", "body": "B", "target": None}],
    ):
        result = client.get("/")
        assert result.data["count"] == 1 and result.data["results"][0]["read"] is False
        assert client.get("/unread-count").data == {"count": 1}
    with patch("notifications.clients.resolve_many", return_value=[None]):
        assert client.get("/").data["results"] == []
    with patch("notifications.clients.resolve_many", side_effect=clients.DependencyUnavailable):
        assert client.get("/").status_code == 503
    assert (
        client.patch("/preferences", {"assignment": False}, format="json").data["assignment"]
        is False
    )
    assert client.patch("/preferences", {"assignment": "false"}, format="json").status_code == 400
    assert client.patch("/preferences", {"other": True}, format="json").status_code == 400
    client.force_authenticate(Actor(uuid4()))
    assert client.post(f"/{n.pk}/read").status_code == 404
    client.force_authenticate(Actor(owner))
    assert client.post(f"/{n.pk}/read").status_code == 200
    assert client.post("/read-all").status_code == 200
    assert client.get("/preferences").status_code == 200


@override_settings(
    NOTIFICATION_MAIL_KEYS={"k1": base64.b64encode(b"k" * 32).decode()},
    NOTIFICATION_FRONTEND_URL="https://web.test",
)
def test_crypto_aad_routes_and_expiry():
    row = persist("identity", encrypted_mail())
    title, body = identity_content(row)
    assert "/auth/activate?key=secret%2Bkey" in body
    row.envelope["event_id"] = str(uuid4())
    with pytest.raises(PermanentFailure):
        identity_content(row)
    reset = persist(
        "identity", encrypted_mail("identity.password_reset.requested", {"uid": "u", "token": "t"})
    )
    assert identity_content(reset)[1] == "https://web.test/auth/reset?uid=u&token=t"
    reset.envelope["data"]["secret"]["expires_at"] = (
        timezone.now() - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(PermanentFailure):
        identity_content(reset)


def test_claim_lease_fencing_recovery_and_unknown():
    row = email_row()
    leased = claim()
    assert leased.pk == row.pk and claim() is None
    EmailDelivery.objects.filter(pk=row.pk).update(
        lease_until=timezone.now() - timedelta(seconds=1)
    )
    again = claim()
    assert again.lease_token != leased.lease_token
    with patch("notifications.tasks.send"):
        deliver(leased)
    row.refresh_from_db()
    assert row.status == "sending"  # stale worker cannot overwrite newer lease
    EmailDelivery.objects.filter(pk=row.pk).update(
        lease_until=timezone.now() - timedelta(seconds=1), smtp_started=True
    )
    assert claim() is None
    row.refresh_from_db()
    assert row.status == "delivery_unknown"


def test_delivery_success_failure_and_unknown():
    row = email_row()
    leased = claim()
    with patch("notifications.tasks.send", side_effect=UnknownDelivery):
        deliver(leased)
    row.refresh_from_db()
    assert row.status == "delivery_unknown"
    EmailDelivery.objects.filter(pk=row.pk).update(status="pending", next_attempt=timezone.now())
    with patch("notifications.tasks.send", side_effect=PermanentFailure("expired")):
        deliver(claim())
    row.refresh_from_db()
    assert row.status == "failed"
    EmailDelivery.objects.filter(pk=row.pk).update(status="pending", next_attempt=timezone.now())
    with patch("notifications.tasks.send"):
        deliver(claim())
    row.refresh_from_db()
    assert row.status == "accepted_by_smtp" and row.accepted_at


@override_settings(NOTIFICATION_EMAILS_PER_DAY=1)
def test_daily_quota_and_transport_retry():
    email_row()

    def sender(row, before_data):
        before_data()

    with patch("notifications.tasks.send", side_effect=sender):
        deliver(claim())
    assert DailyQuota.objects.get().reserved == 1
    second = persist("identity", encrypted_mail())
    process_inbox(second.pk)
    with patch("notifications.tasks.send", side_effect=sender):
        deliver(claim())
    assert EmailDelivery.objects.get(inbox=second).status == "pending"
    assert DailyQuota.objects.get().reserved == 1


@override_settings(
    NOTIFICATION_MAIL_KEYS={"k1": base64.b64encode(b"k" * 32).decode()},
    SMTP_FROM_EMAIL="sender@example.com",
)
def test_smtp_stage_handling():
    row = email_row()
    smtp = Mock()
    smtp.__enter__ = Mock(return_value=smtp)
    smtp.__exit__ = Mock(return_value=False)
    smtp.mail.return_value = (250, b"ok")
    smtp.rcpt.return_value = (250, b"ok")
    smtp.data.return_value = (250, b"accepted")
    before = Mock()
    with (
        patch(
            "notifications.clients.contact",
            return_value={"email": "old@example.com", "account_status": "PENDING_ACTIVATION"},
        ),
        patch("notifications.mail.smtplib.SMTP", return_value=smtp),
    ):
        send(row, before)
        before.assert_called_once()
        assert b"Message-ID: <notification-" in smtp.data.call_args.args[0]
        smtp.data.side_effect = TimeoutError()
        with pytest.raises(UnknownDelivery):
            send(row, before)
        smtp.data.side_effect = None
        smtp.login.side_effect = TimeoutError()
        with pytest.raises(TimeoutError):
            send(row, before)


def test_cleanup_redacts_secret_and_disabled_dispatch():
    row = persist("identity", encrypted_mail())
    row.envelope["data"]["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    row.save()
    cleanup()
    row.refresh_from_db()
    assert row.envelope["data"]["secret"] is None
    with override_settings(EMAIL_ENABLED=False), patch("notifications.tasks.claim") as mocked:
        dispatch()
    mocked.assert_not_called()


@override_settings(
    NOTIFICATION_MAIL_KEYS={"k1": base64.b64encode(b"k" * 32).decode()},
    SMTP_FROM_EMAIL="sender@example.com",
)
def test_smtp_negative_reply_and_accepted_quit_failure():
    import smtplib

    row = email_row()
    smtp = Mock()
    smtp.__enter__ = Mock(return_value=smtp)
    smtp.__exit__ = Mock(return_value=False)
    smtp.mail.return_value = (250, b"ok")
    smtp.rcpt.return_value = (550, b"no")
    with (
        patch(
            "notifications.clients.contact",
            return_value={"email": "old@example.com", "account_status": "PENDING_ACTIVATION"},
        ),
        patch("notifications.mail.smtplib.SMTP", return_value=smtp),
    ):
        with pytest.raises(PermanentFailure):
            send(row, Mock())
        smtp.rcpt.return_value = (450, b"later")
        with pytest.raises(smtplib.SMTPResponseException):
            send(row, Mock())
        smtp.rcpt.return_value = (250, b"ok")
        smtp.data.side_effect = smtplib.SMTPDataError(550, b"no")
        with pytest.raises(PermanentFailure):
            send(row, Mock())
        smtp.data.side_effect = None
        smtp.data.return_value = (250, b"accepted")
        smtp.__exit__.side_effect = TimeoutError()
        send(row, Mock())  # final 250 remains authoritative


def test_delivery_expired_and_ciphertext_redaction():
    row = email_row()
    with patch("notifications.tasks.send", side_effect=PermanentFailure("bad_secret")):
        deliver(claim())
    row.refresh_from_db()
    row.inbox.refresh_from_db()
    assert row.status == "failed" and row.inbox.envelope["data"]["secret"] is None
    from notifications.mail import ExpiredEmail

    second = email_row()
    with patch("notifications.tasks.send", side_effect=ExpiredEmail("secret_expired")):
        deliver(claim())
    second.refresh_from_db()
    assert second.status == "expired"


@override_settings(NOTIFICATION_FRONTEND_URL="https://app.test")
def test_target_urls_are_fixed_routes_and_html_escaped():
    from django.template.loader import render_to_string

    from notifications.mail import target_url

    assert (
        target_url({"kind": "board-issue", "projectId": "p", "issueKey": "T&1"})
        == "https://app.test/projects/p/board?issue=T%261"
    )
    assert (
        target_url({"kind": "backlog", "projectId": "p"}) == "https://app.test/projects/p/backlog"
    )
    assert target_url({"kind": "team-hub", "courseId": "c"}) == "https://app.test/courses/c/team"
    assert target_url(None) is None
    rendered = render_to_string(
        "mail/v1/notification.html",
        {"title": "<script>", "body": "<img>", "url": "https://app.test"},
    )
    assert "<script>" not in rendered and "&lt;img&gt;" in rendered


def test_plain_text_reset_link_preserves_query_parameters_and_html_escapes():
    from urllib.parse import parse_qs, urlsplit

    from django.template.loader import render_to_string

    url = "https://app.test/auth/reset?uid=test-user&token=test-token"
    context = {"title": "Đặt lại mật khẩu", "body": "<test>", "url": url}
    plain = render_to_string("mail/v1/notification.txt", context)
    link = next(line for line in plain.splitlines() if line.startswith("https://"))
    assert parse_qs(urlsplit(link).query) == {"uid": ["test-user"], "token": ["test-token"]}
    html = render_to_string("mail/v1/notification.html", context)
    assert "&amp;token=" in html
    assert "&lt;test&gt;" in html


def test_current_mailbox_must_match_and_work_access_revoked():
    row = email_row()
    with (
        patch(
            "notifications.clients.contact",
            return_value={"email": "changed@example.com", "account_status": "ACTIVE"},
        ),
        pytest.raises(PermanentFailure, match="recipient_email_changed"),
    ):
        send(row, Mock())
    inbox = persist("work", event())
    work = EmailDelivery.objects.create(inbox=inbox, user_id=uuid4())
    with (
        patch(
            "notifications.clients.contact",
            return_value={"email": "me@example.com", "account_status": "ACTIVE"},
        ),
        patch("notifications.clients.resolve", return_value=None),
        pytest.raises(PermanentFailure, match="no_longer_eligible"),
    ):
        send(work, Mock())
    Preference.objects.filter(user_id=work.user_id).update(assignment=False)
    with (
        patch(
            "notifications.clients.contact",
            return_value={"email": "me@example.com", "account_status": "ACTIVE"},
        ),
        pytest.raises(PermanentFailure, match="email_disabled"),
    ):
        send(work, Mock())


def test_health_read_filter_and_validation():
    client = APIClient()
    assert client.get("/healthz").status_code == 200
    owner = uuid4()
    Notification.objects.create(inbox=persist("work", event()), user_id=owner, read=True)
    Notification.objects.create(inbox=persist("work", event()), user_id=owner, read=False)
    Inbox.objects.update(status="processed")
    client.force_authenticate(Actor(owner))

    def results(rows, user_id):
        return [{"title": "T", "body": "B", "target": None} for row in rows]

    with patch("notifications.clients.resolve_many", side_effect=results):
        assert client.get("/?read=true").data["count"] == 1
        assert client.get("/?read=false").data["count"] == 1
        assert client.get("/?read=invalid").status_code == 400
        assert client.get("/unread-count").data["count"] == 1


def test_public_validation_and_dependency_messages_are_vietnamese():
    client = APIClient()
    anonymous = client.get("/")
    assert anonymous.status_code == 401
    assert str(anonymous.data["detail"]) == "Bạn cần đăng nhập để xem thông báo."
    assert anonymous["WWW-Authenticate"] == "Bearer"
    assert anonymous.data["detail"].code == "not_authenticated"
    owner = uuid4()
    client.force_authenticate(Actor(owner))
    invalid = client.patch("/preferences", {"mention": "yes"}, format="json")
    assert invalid.status_code == 400
    assert "Mỗi tùy chọn phải là true hoặc false." in str(invalid.data)
    valid = client.patch("/preferences", {"mention": False}, format="json")
    assert valid.status_code == 200 and valid.data["mention"] is False
    row = persist("work", event())
    row.status = "processed"
    row.save()
    Notification.objects.create(inbox=row, user_id=owner)
    with patch("notifications.clients.resolve_many", side_effect=clients.DependencyUnavailable):
        failed = client.get("/")
    assert failed.status_code == 503
    assert str(failed.data["detail"]) == "Không thể tải thông báo lúc này."


@pytest.mark.parametrize(
    "method,path,body,content_type,status,fragment",
    [
        ("get", "/?page=invalid", None, None, 404, "Không tìm thấy"),
        ("delete", "/preferences", None, None, 405, "không được hỗ trợ"),
        ("patch", "/preferences", "{", "application/json", 400, "định dạng JSON"),
        ("patch", "/preferences", "test", "text/plain", 415, "định dạng JSON"),
    ],
)
def test_framework_failures_preserve_status_with_vietnamese_detail(
    method, path, body, content_type, status, fragment
):
    client = APIClient()
    client.force_authenticate(Actor(uuid4()))
    kwargs = {"data": body, "content_type": content_type} if content_type else {}
    with patch("notifications.clients.resolve_many", return_value=[]):
        response = getattr(client, method)(path, **kwargs)
    assert response.status_code == status
    assert fragment in str(response.data["detail"])
