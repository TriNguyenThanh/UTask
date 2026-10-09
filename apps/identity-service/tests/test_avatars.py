from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from django.db import connection
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient

from accounts.avatar_storage import AvatarStorage
from accounts.models import OutboxEvent
from accounts.services.avatars import receipt_client, receipt_key
from tests.helpers import create_user, login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]
PRESIGN = "/users/me/avatar/presigned-url"
CONFIRM = "/users/me/avatar/confirm"


@pytest.fixture
def avatar_client(settings, monkeypatch):
    settings.ROOT_URLCONF = "tests.avatar_urls"
    settings.IDENTITY_R2_PUBLIC_URL = "https://avatars.example.test"
    settings.IDENTITY_R2_BUCKET = "test-bucket"
    storage = Mock()
    storage.generate_presigned_url.return_value = "https://upload.example.test/signed"

    def head(**kwargs):
        assert not connection.in_atomic_block
        return {"ContentType": "image/png", "ContentLength": 100}

    storage.head_object.side_effect = head
    monkeypatch.setattr(AvatarStorage, "client", staticmethod(lambda: storage))
    client = APIClient()
    user = create_user()
    login(client, user)
    return client, user, storage


def presign(client, **extra):
    return client.post(
        PRESIGN,
        {"file_name": "photo.png", "content_type": "image/png", "file_size": 100, **extra},
        format="json",
    )


def test_avatar_receipt_head_update_noop_and_no_client_url(avatar_client):
    client, user, storage = avatar_client
    result = presign(client)
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["file_key"].startswith(f"avatars/{user.pk}/")
    assert data["expires_in"] == 300
    assert receipt_client().ttl(receipt_key(data["file_key"])) > 0
    response = client.post(CONFIRM, {"file_key": data["file_key"]}, format="json")
    assert response.status_code == 200
    assert response.json()["data"]["avatar_url"] == data["public_url"]
    user.profile.refresh_from_db()
    assert user.profile.avatar_url == data["public_url"]
    assert client.post(CONFIRM, {"file_key": data["file_key"]}, format="json").status_code == 200
    assert storage.head_object.call_count == 1
    assert OutboxEvent.objects.filter(event_type="identity.user.updated").count() == 1
    assert receipt_client().get(receipt_key(data["file_key"])) is None
    assert (
        client.post(
            CONFIRM,
            {"file_key": data["file_key"], "avatar_url": "https://evil.test"},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "extra,code",
    [
        ({"content_type": "image/gif"}, "INVALID_IMAGE_TYPE"),
        ({"file_size": 5242881}, "FILE_SIZE_EXCEEDS_LIMIT"),
        ({"file_size": 0}, "VALIDATION_ERROR"),
    ],
)
def test_avatar_validation(avatar_client, extra, code):
    client, _, storage = avatar_client
    result = presign(client, **extra)
    assert result.status_code == 400 and result.json()["error"]["code"] == code
    storage.generate_presigned_url.assert_not_called()


def test_avatar_other_owner_expired_receipt_and_metadata(avatar_client):
    client, user, storage = avatar_client
    key = presign(client).json()["data"]["file_key"]
    other = APIClient()
    login(other, create_user())
    assert (
        other.post(CONFIRM, {"file_key": key}, format="json").json()["error"]["code"]
        == "INVALID_UPLOAD_REFERENCE"
    )
    storage.head_object.side_effect = None
    storage.head_object.return_value = {"ContentType": "image/png", "ContentLength": 101}
    result = client.post(CONFIRM, {"file_key": key}, format="json")
    assert (
        result.status_code == 400 and result.json()["error"]["code"] == "UPLOAD_METADATA_MISMATCH"
    )
    receipt_client().delete(receipt_key(key))
    assert (
        client.post(CONFIRM, {"file_key": key}, format="json").json()["error"]["code"]
        == "INVALID_UPLOAD_REFERENCE"
    )
    user.profile.refresh_from_db()
    assert user.profile.avatar_url is None


@pytest.mark.parametrize(
    "error,status,code",
    [
        (ClientError({"Error": {"Code": "404"}}, "HeadObject"), 404, "UPLOAD_NOT_FOUND"),
        (
            EndpointConnectionError(endpoint_url="https://r2.example.test"),
            503,
            "STORAGE_UNAVAILABLE",
        ),
    ],
)
def test_avatar_storage_failure_never_updates_profile(avatar_client, error, status, code):
    client, user, storage = avatar_client
    key = presign(client).json()["data"]["file_key"]
    storage.head_object.side_effect = error
    result = client.post(CONFIRM, {"file_key": key}, format="json")
    assert result.status_code == status and result.json()["error"]["code"] == code
    user.profile.refresh_from_db()
    assert user.profile.avatar_url is None
    receipt_client().delete(receipt_key(key))


def test_avatar_redis_outage_no_success(avatar_client, monkeypatch):
    client, _, _ = avatar_client
    broken = Mock()
    broken.setex.side_effect = RedisConnectionError()
    monkeypatch.setattr("accounts.services.avatars.receipt_client", lambda: broken)
    result = presign(client)
    assert result.status_code == 503 and result.json()["error"]["code"] == "IDENTITY_UNAVAILABLE"
