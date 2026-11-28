"""Business OAuth binding adapter: Django cache with atomic single-use claim."""

import hashlib
import json
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from redis.exceptions import RedisError

from common.errors import CoreAPIError

COOKIE = "oauth_context"
OAUTH_CONTEXT_TTL = 600


def context_key(state: str) -> str:
    return "identity:oauth:" + hashlib.sha256(state.encode()).hexdigest()


def create_context(provider, redirect_uri, verifier, nonce, actor=None):
    state, cookie = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    record = {
        "provider": provider,
        "redirect_uri": redirect_uri,
        "verifier": verifier,
        "nonce": nonce,
        "cookie_hash": hashlib.sha256(cookie.encode()).hexdigest(),
        "actor": str(actor) if actor else None,
        "expires_at": (timezone.now() + timedelta(seconds=OAUTH_CONTEXT_TTL)).isoformat(),
    }
    try:
        created = cache.add(context_key(state), json.dumps(record), timeout=OAUTH_CONTEXT_TTL)
    except (RedisError, ConnectionError, TimeoutError) as exc:
        raise CoreAPIError(
            "IDENTITY_UNAVAILABLE",
            "Không thể khởi tạo hoặc kiểm tra phiên đăng nhập bên ngoài.",
            status_code=503,
        ) from exc
    if not created:
        raise CoreAPIError(
            "IDENTITY_UNAVAILABLE",
            "Không thể khởi tạo hoặc kiểm tra phiên đăng nhập bên ngoài.",
            status_code=503,
        )
    return state, cookie


def consume_context(request, provider, *, actor=None):
    state = request.data.get("state")
    if not isinstance(state, str) or not state or len(state) > 128:
        raise CoreAPIError(
            "OAUTH_STATE_INVALID",
            "Yêu cầu đăng nhập bên ngoài không hợp lệ hoặc đã hết hạn. Vui lòng bắt đầu lại.",
        )
    key = context_key(state)
    consumed_key = f"{key}:consumed"
    try:
        raw = cache.get(key)
        record = raw if isinstance(raw, dict) else (json.loads(raw) if raw else None)
        cookie_hash = hashlib.sha256(request.COOKIES.get(COOKIE, "").encode()).hexdigest()
        expires_at = parse_datetime(record.get("expires_at", "")) if record else None
        if (
            not record
            or expires_at is None
            or expires_at <= timezone.now()
            or record["provider"] != provider
            or record["redirect_uri"] != request.data.get("redirect_uri")
            or record["actor"] != (str(actor) if actor else None)
            or not secrets.compare_digest(record["cookie_hash"], cookie_hash)
        ):
            raise CoreAPIError(
                "OAUTH_STATE_INVALID",
                "Yêu cầu đăng nhập bên ngoài không hợp lệ hoặc đã hết hạn. Vui lòng bắt đầu lại.",
            )
        if not cache.add(consumed_key, 1, timeout=OAUTH_CONTEXT_TTL):
            raise CoreAPIError(
                "OAUTH_STATE_INVALID",
                "Yêu cầu đăng nhập bên ngoài đã được sử dụng. Vui lòng bắt đầu lại.",
            )
        cache.delete(key)
        return record
    except CoreAPIError:
        raise
    except (RedisError, ConnectionError, TimeoutError) as exc:
        raise CoreAPIError(
            "IDENTITY_UNAVAILABLE",
            "Không thể khởi tạo hoặc kiểm tra phiên đăng nhập bên ngoài.",
            status_code=503,
        ) from exc
