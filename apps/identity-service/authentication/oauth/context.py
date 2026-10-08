"""Business OAuth binding adapter: Redis WATCH makes context consumption single-use."""

import hashlib
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from redis import Redis
from redis.exceptions import RedisError, WatchError

from common.errors import IdentityAPIError

COOKIE = "oauth_context"


def client():
    return Redis.from_url(settings.IDENTITY_REDIS_URL, socket_connect_timeout=2, socket_timeout=2)


def context_key(state):
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
        "expires_at": (timezone.now() + timedelta(seconds=600)).isoformat(),
    }
    try:
        client().set(context_key(state), json.dumps(record), ex=600, nx=True)
    except RedisError as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE", "OAuth context unavailable.", status_code=503
        ) from exc
    return state, cookie


def consume_context(request, provider, *, actor=None):
    state = request.data.get("state")
    if not isinstance(state, str) or not state or len(state) > 128:
        raise IdentityAPIError("OAUTH_STATE_INVALID", "Invalid OAuth context.")
    key = context_key(state)
    try:
        with client().pipeline() as pipe:
            pipe.watch(key)
            raw = pipe.get(key)
            record = json.loads(raw) if raw else None
            cookie_hash = hashlib.sha256(request.COOKIES.get(COOKIE, "").encode()).hexdigest()
            if (
                not record
                or record["provider"] != provider
                or record["redirect_uri"] != request.data.get("redirect_uri")
                or record["actor"] != (str(actor) if actor else None)
                or not secrets.compare_digest(record["cookie_hash"], cookie_hash)
            ):
                raise IdentityAPIError("OAUTH_STATE_INVALID", "Invalid OAuth context.")
            pipe.multi()
            pipe.delete(key)
            pipe.execute()
            return record
    except WatchError as exc:
        raise IdentityAPIError("OAUTH_STATE_INVALID", "OAuth context already consumed.") from exc
    except RedisError as exc:
        raise IdentityAPIError(
            "IDENTITY_UNAVAILABLE", "OAuth context unavailable.", status_code=503
        ) from exc
