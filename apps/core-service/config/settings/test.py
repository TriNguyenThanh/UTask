"""Deterministic isolated test settings for UTask Core Service."""

import base64
import os

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-core-service-secret-key")
os.environ.setdefault("DJANGO_DEBUG", "false")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

from .base import *  # noqa: E402, F403

_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
_public_pem = (
    _private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
)

SIMPLE_JWT = {  # noqa: F405
    **SIMPLE_JWT,  # noqa: F405
    "SIGNING_KEY": _private_pem,
    "VERIFYING_KEY": _public_pem,
}

IDENTITY_MAIL_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
IDENTITY_MAIL_KEY_ID = "test-mail-key-1"
CLASSROOM_ACCESS_CODE_HMAC_KEY = "test-classroom-access-code-hmac-key"
IDENTITY_SERVICE_KEYS = {
    "ai": "test-ai-identity-service-key-000000000000",
    "integration": "test-integration-identity-service-key-00",
}
IDENTITY_NOTIFICATION_SERVICE_KEY = "test-notification-identity-key-0000000"
NOTIFICATION_SERVICE_TOKEN = "test-notification-service-token-000000"

DATABASES["default"].update(  # noqa: F405
    {
        "NAME": os.environ.get("CORE_TEST_DB_NAME", os.environ.get("DATABASE_NAME", "postgres")),
        "USER": os.environ.get("CORE_TEST_DB_USER", os.environ.get("POSTGRES_USER", "postgres")),
        "PASSWORD": os.environ.get(
            "CORE_TEST_DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "postgres")
        ),
        "HOST": os.environ.get("CORE_TEST_DB_HOST", os.environ.get("POSTGRES_HOST", "127.0.0.1")),
        "PORT": os.environ.get("CORE_TEST_DB_PORT", os.environ.get("POSTGRES_PORT", "5432")),
        "TEST": {"NAME": os.environ.get("CORE_TEST_DATABASE", "test_core_ci")},
    }
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "utask-core-tests",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
