import base64
import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from notifications import clients
from notifications.models import Preference
from notifications.services import WORK_EVENTS


class PermanentFailure(Exception):
    pass


class ExpiredEmail(PermanentFailure):
    pass


class UnknownDelivery(Exception):
    pass


def identity_content(inbox):
    envelope = inbox.envelope
    data = envelope["data"]
    try:
        expiry = parse_datetime(data["expires_at"])
        if expiry and timezone.is_aware(expiry) and expiry <= timezone.now():
            raise ExpiredEmail("secret_expired")
        secret = data["secret"]
        expires = secret["expires_at"]
        expiration = parse_datetime(expires)
        if (
            expiration is None
            or timezone.is_naive(expiration)
            or expiration <= timezone.now()
            or expires != data["expires_at"]
        ):
            raise ValueError()
        keys = settings.NOTIFICATION_MAIL_KEYS
        if isinstance(keys, str):
            keys = json.loads(keys)
        key = base64.b64decode(keys[secret["key_id"]], validate=True)
        nonce = base64.b64decode(secret["nonce"], validate=True)
        if len(key) != 32 or len(nonce) != 12:
            raise ValueError()
        aad = json.dumps(
            [str(envelope["event_id"]), envelope["event_type"], str(data["user_id"]), expires],
            separators=(",", ":"),
        ).encode()
        plain = json.loads(
            AESGCM(key).decrypt(nonce, base64.b64decode(secret["ciphertext"], validate=True), aad)
        )
        if envelope["event_type"] == "identity.password_reset.requested":
            if not all(isinstance(plain.get(k), str) and plain[k] for k in ["uid", "token"]):
                raise ValueError()
            return (
                "Đặt lại mật khẩu UTask",
                settings.NOTIFICATION_FRONTEND_URL
                + "/auth/reset?"
                + urlencode({"uid": plain["uid"], "token": plain["token"]}),
            )
        if not isinstance(plain.get("key"), str) or not plain["key"]:
            raise ValueError()
        return (
            "Kích hoạt tài khoản UTask",
            settings.NOTIFICATION_FRONTEND_URL
            + "/auth/activate?"
            + urlencode({"key": plain["key"]}),
        )
    except ExpiredEmail:
        raise
    except Exception as exc:
        # Do not expose provider errors or decrypted secrets in logs/state.
        raise PermanentFailure("invalid_secret") from exc


def send(delivery, before_data):
    user = clients.contact(delivery.user_id)
    if user is None:
        raise PermanentFailure("recipient_unavailable")
    inbox = delivery.inbox
    if inbox.source == "identity":
        if user["email"].casefold() != inbox.envelope["data"]["email"].casefold():
            raise PermanentFailure("recipient_email_changed")
        subject, url = identity_content(inbox)
        body = "Dùng liên kết sau để hoàn tất yêu cầu của bạn. Liên kết có thời hạn."
    else:
        if user["account_status"] != "ACTIVE":
            raise PermanentFailure("recipient_inactive")
        category = WORK_EVENTS[inbox.envelope["event_type"]]
        pref, _ = Preference.objects.get_or_create(user_id=delivery.user_id)
        if not category or not getattr(pref, category):
            raise PermanentFailure("email_disabled")
        result = clients.resolve(inbox, delivery.user_id)
        if result is None:
            raise PermanentFailure("no_longer_eligible")
        subject, body = result["title"], result["body"]
        url = target_url(result.get("target"))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = user["email"]
    message["Message-ID"] = f"<notification-{delivery.id}@utask.internal>"
    context = {"title": subject, "body": body, "url": url}
    message.set_content(render_to_string("mail/v1/notification.txt", context))
    message.add_alternative(render_to_string("mail/v1/notification.html", context), subtype="html")
    started = False
    accepted = False
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            code, _ = smtp.mail(settings.SMTP_FROM_EMAIL)
            if code != 250:
                raise smtplib.SMTPSenderRefused(code, "rejected", settings.SMTP_FROM_EMAIL)
            code, _ = smtp.rcpt(user["email"])
            if code not in (250, 251):
                raise smtplib.SMTPResponseException(code, "recipient_rejected")
            before_data()
            started = True
            try:
                code, _ = smtp.data(message.as_bytes())
            except smtplib.SMTPDataError:
                # smtplib raises this when the server rejects the DATA command
                # before receiving the message, so acceptance is not ambiguous.
                started = False
                raise
            if code != 250:
                # Explicit negative response means server did not accept message.
                started = False
                raise smtplib.SMTPDataError(code, "rejected")
            accepted = True
            return  # successful DATA response is authoritative, QUIT may fail
    except (OSError, smtplib.SMTPException) as exc:
        if accepted:
            return
        if started:
            raise UnknownDelivery("smtp_acceptance_unknown") from exc
        if isinstance(exc, smtplib.SMTPResponseException) and exc.smtp_code >= 500:
            raise PermanentFailure("smtp_permanent_rejection") from exc
        raise


def target_url(target):
    if target is None:
        return None
    if not clients.valid_target(target):
        raise PermanentFailure("invalid_target")
    kind = target["kind"]
    if kind in {"team-hub", "team-formation", "join-request", "course-deadline"}:
        path = "/courses/" + quote(target["courseId"], safe="") + "/team"
    else:
        path = "/projects/" + quote(target["projectId"], safe="")
        if kind == "board-issue":
            path += "/board?" + urlencode({"issue": target["issueKey"]})
        else:
            path += "/" + kind
    return settings.NOTIFICATION_FRONTEND_URL + path
