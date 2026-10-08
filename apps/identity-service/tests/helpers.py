"""Acceptance uses real library login and Bearer authentication, never force_authenticate."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from allauth.account.models import EmailAddress
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import close_old_connections, connections

from accounts.models import User

PASSWORD = "StrongPassword123!"
NEW_PASSWORD = "NewStrongPassword456!"


def create_user(**kwargs):
    unique = uuid4().hex
    user = User.objects.create_user(
        email=f"{unique}@example.edu.vn", username=unique, password=PASSWORD, **kwargs
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def login(client, user, password=PASSWORD, *, field="email"):
    response = client.post(
        "/api/v1/auth/login",
        {field: getattr(user, field), "password": password, "device_name": "Acceptance browser"},
        format="json",
    )
    assert response.status_code == 200, response.json()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + response.json()["data"]["access"])
    return response


def refresh_from_body(client, raw):
    client.cookies.clear()
    return client.post("/api/v1/auth/refresh", {"refresh": raw}, format="json")


def mail_secret(event):
    """Read test outbox mail; this does not assert Notification delivery."""
    envelope = event.data
    data = envelope["data"]
    secret = data["secret"]
    aad = json.dumps(
        [envelope["event_id"], envelope["event_type"], data["user_id"], data["expires_at"]],
        separators=(",", ":"),
    ).encode()
    plaintext = AESGCM(base64.b64decode(settings.IDENTITY_MAIL_KEY)).decrypt(
        base64.b64decode(secret["nonce"]), base64.b64decode(secret["ciphertext"]), aad
    )
    return json.loads(plaintext)


def run_concurrent(*operations):
    """Start operations together on independent connections and always close them."""
    barrier = Barrier(len(operations))

    def execute(operation):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(execute, operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]
