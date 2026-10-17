import hashlib
import hmac
import secrets

from django.conf import settings

from common.errors import ClassroomError


def code_hash(value):
    key = settings.CLASSROOM_ACCESS_CODE_HMAC_KEY
    if not key:
        raise ClassroomError(
            "ACCESS_CODE_UNAVAILABLE", "Chưa thể cấp hoặc kiểm tra mã tham gia.", 503
        )
    return hmac.new(key.encode(), str(value).strip().upper().encode(), hashlib.sha256).hexdigest()


def generate_code():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(12))
