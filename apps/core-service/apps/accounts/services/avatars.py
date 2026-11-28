"""Avatar receipt binds owner/session/key/metadata; remote HEAD precedes the write TX."""

import hashlib
import json
import re
from time import time
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from redis.exceptions import RedisError

from apps.accounts.serializers.avatars import IMAGE_EXTENSIONS
from apps.accounts.services.account_access import account_audit, lock_accounts
from apps.messaging.services.outbox import emit_identity_user
from common.errors import CoreAPIError
from infrastructure.storage import storage_client

AVATAR_RECEIPT_TTL = 300


def receipt_key(key: str) -> str:
    return "identity:avatar:" + hashlib.sha256(key.encode()).hexdigest()


def public_url(key: str) -> str:
    return settings.IDENTITY_R2_PUBLIC_URL.rstrip("/") + "/" + key


def presign_avatar(request, data):
    extension = IMAGE_EXTENSIONS[data["content_type"]]
    key = f"avatars/{request.user.pk}/{int(time())}_{uuid4().hex}.{extension}"
    url = storage_client().presign_avatar(key, data["content_type"], data["file_size"])
    record = {
        "user_id": str(request.user.pk),
        "session_id": request.auth["session_id"],
        "file_key": key,
        "content_type": data["content_type"],
        "file_size": data["file_size"],
    }
    try:
        cache.set(receipt_key(key), json.dumps(record), timeout=AVATAR_RECEIPT_TTL)
    except (RedisError, ConnectionError, TimeoutError) as exc:
        raise CoreAPIError(
            "IDENTITY_UNAVAILABLE",
            "Không thể tạo yêu cầu tải ảnh. Vui lòng thử lại.",
            status_code=503,
        ) from exc
    return {
        "upload_url": url,
        "public_url": public_url(key),
        "file_key": key,
        "expires_in": AVATAR_RECEIPT_TTL,
    }


def confirm_avatar(request, key):
    if not re.fullmatch(rf"avatars/{request.user.pk}/[0-9]+_[0-9a-f]{{32}}\.(jpg|png|webp)", key):
        raise CoreAPIError("INVALID_UPLOAD_REFERENCE", "Thông tin ảnh tải lên không hợp lệ.")
    url = public_url(key)
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        if user.profile.avatar_url == url:
            return {"avatar_url": url}
    try:
        raw = cache.get(receipt_key(key))
    except (RedisError, ConnectionError, TimeoutError) as exc:
        raise CoreAPIError(
            "IDENTITY_UNAVAILABLE",
            "Không thể kiểm tra yêu cầu tải ảnh. Vui lòng thử lại.",
            status_code=503,
        ) from exc
    record = raw if isinstance(raw, dict) else (json.loads(raw) if raw else None)
    if (
        not record
        or record["user_id"] != str(request.user.pk)
        or record["session_id"] != request.auth["session_id"]
        or record["file_key"] != key
    ):
        raise CoreAPIError(
            "INVALID_UPLOAD_REFERENCE",
            "Yêu cầu tải ảnh không hợp lệ hoặc đã hết hạn. Vui lòng tải lại ảnh.",
        )
    metadata = storage_client().head_avatar(key)  # Real remote call, outside database transaction.
    if (
        metadata.get("ContentLength") != record["file_size"]
        or metadata.get("ContentType") != record["content_type"]
    ):
        raise CoreAPIError(
            "UPLOAD_METADATA_MISMATCH",
            "Loại hoặc dung lượng ảnh đã tải lên không khớp với yêu cầu ban đầu.",
        )
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        if user.profile.avatar_url != url:
            user.profile.avatar_url = url
            user.profile.save(update_fields=("avatar_url", "updated_at"))
            account_audit(request, user, "AVATAR_UPDATED")
            emit_identity_user(user, "identity.user.updated")
    try:
        cache.delete(receipt_key(key))
    except (RedisError, ConnectionError, TimeoutError):
        pass  # DB commit is authoritative; repeated confirm of the current avatar is a no-op.
    return {"avatar_url": url}


def _extract_owned_avatar_key(user_id, avatar_url: str | None) -> str | None:
    if not avatar_url or not getattr(settings, "IDENTITY_R2_PUBLIC_URL", ""):
        return None
    prefix = settings.IDENTITY_R2_PUBLIC_URL.rstrip("/") + "/"
    if not avatar_url.startswith(prefix):
        return None
    key = avatar_url.removeprefix(prefix)
    if re.fullmatch(rf"avatars/{user_id}/[0-9]+_[0-9a-f]{{32}}\.(jpg|png|webp)", key):
        return key
    return None


def delete_avatar(request):
    old_key = None
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        current_url = user.profile.avatar_url
        if current_url is not None:
            old_key = _extract_owned_avatar_key(user.pk, current_url)
            user.profile.avatar_url = None
            user.profile.save(update_fields=("avatar_url", "updated_at"))
            account_audit(request, user, "AVATAR_DELETED")
            emit_identity_user(user, "identity.user.updated")
    if old_key is not None:
        storage_client().delete_avatar(old_key)  # Best-effort R2 cleanup outside DB transaction.
    return {"avatar_url": None}
