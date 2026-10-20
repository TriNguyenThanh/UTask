"""Mail encryption and key validation; event construction belongs to outbox."""

import base64
import json
import secrets
from copy import deepcopy

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.errors import IdentityAPIError


def mail_key():
    try:
        key = base64.b64decode(settings.IDENTITY_MAIL_KEY or "", validate=True)
        if len(key) != 32 or not settings.IDENTITY_MAIL_KEY_ID:
            raise ValueError()
        return key
    except (ValueError, TypeError) as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE",
            "Chưa thể tạo hướng dẫn xác thực cho tài khoản. Vui lòng liên hệ người quản trị.",
            status_code=503,
        ) from exc


def encrypt_mail_payload(key, event_id, event_type, user_id, expires, secret):
    aad = json.dumps(
        [str(event_id), event_type, str(user_id), expires], separators=(",", ":")
    ).encode()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, json.dumps(secret, separators=(",", ":")).encode(), aad)
    return {
        "key_id": settings.IDENTITY_MAIL_KEY_ID,
        "expires_at": expires,
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(encrypted).decode(),
    }


def redact_expired_mail_secret(envelope, now):
    data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
    secret = data.get("secret") if isinstance(data, dict) else None
    if not isinstance(secret, dict):
        return envelope, False
    try:
        expiration = parse_datetime(secret.get("expires_at", ""))
    except (TypeError, ValueError):
        return envelope, False
    if expiration is None or timezone.is_naive(expiration) or expiration > now:
        return envelope, False
    result = deepcopy(envelope)
    result["data"]["secret"] = None
    return result, True
