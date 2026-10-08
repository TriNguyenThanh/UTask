"""Avatar receipt binds owner/session/key/metadata; remote HEAD precedes the write TX."""

import hashlib
import json
import re
from time import time
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from redis import Redis
from redis.exceptions import RedisError

from accounts.avatar_storage import AvatarStorage
from accounts.serializers.avatars import IMAGE_EXTENSIONS
from accounts.services.account_access import account_audit, lock_accounts
from common.errors import IdentityAPIError
from messaging.outbox import emit_user


def receipt_client():
    return Redis.from_url(settings.IDENTITY_REDIS_URL, socket_timeout=3, socket_connect_timeout=3)


def receipt_key(key):
    return "identity:avatar:" + hashlib.sha256(key.encode()).hexdigest()


def public_url(key):
    return settings.IDENTITY_R2_PUBLIC_URL.rstrip("/") + "/" + key


def presign_avatar(request, data):
    extension = IMAGE_EXTENSIONS[data["content_type"]]
    key = f"avatars/{request.user.pk}/{int(time())}_{uuid4().hex}.{extension}"
    url = AvatarStorage.presign(key, data["content_type"], data["file_size"])
    record = {
        "user_id": str(request.user.pk),
        "session_id": request.auth["session_id"],
        "file_key": key,
        "content_type": data["content_type"],
        "file_size": data["file_size"],
    }
    try:
        receipt_client().setex(receipt_key(key), 300, json.dumps(record))
    except RedisError as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE", "Không thể lưu receipt tải ảnh.", status_code=503
        ) from exc
    return {"upload_url": url, "public_url": public_url(key), "file_key": key, "expires_in": 300}


def confirm_avatar(request, key):
    if not re.fullmatch(rf"avatars/{request.user.pk}/[0-9]+_[0-9a-f]{{32}}\.(jpg|png|webp)", key):
        raise IdentityAPIError("INVALID_UPLOAD_REFERENCE", "File key không hợp lệ.")
    url = public_url(key)
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        if user.profile.avatar_url == url:
            return {"avatar_url": url}
    try:
        raw = receipt_client().get(receipt_key(key))
    except RedisError as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE", "Không thể đọc receipt tải ảnh.", status_code=503
        ) from exc
    record = json.loads(raw) if raw else None
    if (
        not record
        or record["user_id"] != str(request.user.pk)
        or record["session_id"] != request.auth["session_id"]
        or record["file_key"] != key
    ):
        raise IdentityAPIError("INVALID_UPLOAD_REFERENCE", "Receipt không hợp lệ hoặc đã hết hạn.")
    metadata = AvatarStorage.head(key)  # Real remote call, outside database transaction.
    if (
        metadata.get("ContentLength") != record["file_size"]
        or metadata.get("ContentType") != record["content_type"]
    ):
        raise IdentityAPIError("UPLOAD_METADATA_MISMATCH", "Thông tin ảnh khác với receipt.")
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        if user.profile.avatar_url != url:
            user.profile.avatar_url = url
            user.profile.save(update_fields=("avatar_url", "updated_at"))
            account_audit(request, user, "AVATAR_UPDATED")
            emit_user(user, "identity.user.updated")
    try:
        receipt_client().delete(receipt_key(key))
    except RedisError:
        pass  # DB commit is authoritative; repeated confirm of the current avatar is a no-op.
    return {"avatar_url": url}
