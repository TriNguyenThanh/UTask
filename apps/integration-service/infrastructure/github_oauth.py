"""Identity-only GitHub OAuth; provider credentials never leave this adapter."""

import json
import re
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from rest_framework.exceptions import APIException

from apps.github_accounts.validation import GITHUB_ID_PATTERN, GITHUB_USERNAME_PATTERN

MAX_RESPONSE_BYTES = 65_536


class GitHubOAuthUnavailable(APIException):
    status_code = 503
    default_detail = "Không thể xác minh tài khoản GitHub lúc này."
    default_code = "GITHUB_UNAVAILABLE"


class GitHubOAuthClient:
    def _configuration(self):
        values = tuple(
            getattr(settings, name, "")
            for name in (
                "INTEGRATION_GITHUB_CLIENT_ID",
                "INTEGRATION_GITHUB_CLIENT_SECRET",
                "INTEGRATION_GITHUB_REDIRECT_URI",
            )
        )
        if any(
            not isinstance(value, str)
            or not value
            or len(value) > 2048
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
            for value in values
        ):
            raise GitHubOAuthUnavailable()
        try:
            parsed = urlsplit(values[2])
            valid = (
                parsed.hostname
                and (
                    parsed.scheme == "https"
                    or (
                        parsed.scheme == "http"
                        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                    )
                )
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and parsed.port != 0
            )
        except ValueError:
            valid = False
        if not valid:
            raise GitHubOAuthUnavailable()
        return values

    def authorization_url(self, *, state, code_challenge):
        client_id, _, redirect_uri = self._configuration()
        if (
            not isinstance(state, str)
            or not re.fullmatch(r"[A-Za-z0-9_~-]{32,256}", state)
            or not isinstance(code_challenge, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge)
        ):
            raise GitHubOAuthUnavailable()
        return "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )

    def _request_json(self, method, url, **kwargs):
        try:
            with requests.request(
                method, url, timeout=(2, 3), allow_redirects=False, stream=True, **kwargs
            ) as response:
                if response.status_code != 200:
                    raise ValueError()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError()
                payload = json.loads(body)
                if not isinstance(payload, dict) or "error" in payload:
                    raise ValueError()
                return payload
        except (requests.RequestException, ValueError, TypeError, UnicodeError):
            raise GitHubOAuthUnavailable() from None

    def verify(self, *, code, verifier):
        client_id, secret, redirect_uri = self._configuration()
        if (
            not isinstance(code, str)
            or not re.fullmatch(r"[\x21-\x7e]{1,1024}", code)
            or not isinstance(verifier, str)
            or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
        ):
            raise GitHubOAuthUnavailable()
        payload = self._request_json(
            "POST",
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": verifier,
            },
        )
        token = payload.get("access_token")
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"[A-Za-z0-9_\-.]{1,8192}", token)
            or not isinstance(payload.get("token_type"), str)
            or payload["token_type"].lower() != "bearer"
        ):
            raise GitHubOAuthUnavailable()
        user = self._request_json(
            "GET",
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        github_id, login = user.get("id"), user.get("login")
        if (
            type(github_id) is not int
            or not re.fullmatch(GITHUB_ID_PATTERN, str(github_id))
            or not isinstance(login, str)
            or not 1 <= len(login) <= 39
            or not re.fullmatch(GITHUB_USERNAME_PATTERN, login)
        ):
            raise GitHubOAuthUnavailable()
        return str(github_id), login
