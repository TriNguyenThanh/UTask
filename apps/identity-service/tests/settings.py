"""Test-only RSA/mail keys. Production config never imports this module."""

import base64
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "isolated-identity-tests-only")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from config.settings import *  # noqa: F403, E402

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "SIGNING_KEY": _key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode(),
    "VERIFYING_KEY": _key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode(),
}
IDENTITY_MAIL_KEY = base64.b64encode(b"a" * 32).decode()
IDENTITY_MAIL_KEY_ID = "isolated-test-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": os.environ.get("IDENTITY_TEST_DB_NAME", "test_identity_library_auth")
}  # noqa: F405

IDENTITY_REDIS_URL = os.environ.get("IDENTITY_TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
