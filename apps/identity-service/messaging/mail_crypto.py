"""Mail encryption and key validation; event construction belongs to outbox."""

import base64
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

from common.errors import IdentityAPIError


def mail_key():
    try:
        key = base64.b64decode(settings.IDENTITY_MAIL_KEY or "", validate=True)
        if len(key) != 32 or not settings.IDENTITY_MAIL_KEY_ID:
            raise ValueError()
        return key
    except (ValueError, TypeError) as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE", "Mail encryption is not configured.", status_code=503
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
