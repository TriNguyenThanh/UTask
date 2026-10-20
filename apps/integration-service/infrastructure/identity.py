"""Validate the actor using Identity's existing user endpoint, without caller changes."""

import json
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import requests
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

from common.api_errors import IdentityUnavailable

MAX_IDENTITY_RESPONSE_BYTES = 65_536


@dataclass(frozen=True)
class Principal:
    id: UUID

    @property
    def is_authenticated(self):
        return True


class IdentityUserClient:
    def current_user(self, bearer):
        base = settings.INTEGRATION_IDENTITY_URL
        try:
            parsed = urlsplit(base)
        except ValueError as exc:
            raise IdentityUnavailable() from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise IdentityUnavailable()
        try:
            with requests.get(
                base.rstrip("/") + "/users/me",
                headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"},
                timeout=(2, 3),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in {401, 403}:
                    raise AuthenticationFailed("Phiên đăng nhập không hợp lệ hoặc đã bị thu hồi.")
                if response.status_code != 200:
                    raise IdentityUnavailable()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > MAX_IDENTITY_RESPONSE_BYTES:
                        raise IdentityUnavailable()
                payload = json.loads(body)
                if payload.get("success") is not True:
                    raise ValueError()
                user_id = UUID(payload["data"]["id"])
                if user_id.int == 0:
                    raise ValueError()
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise IdentityUnavailable() from exc
        return Principal(id=user_id)
