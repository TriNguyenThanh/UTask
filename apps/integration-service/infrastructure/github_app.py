"""GitHub App user-token adapter. URLs and response fields are allowlisted."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.github_accounts.validation import GITHUB_ID_PATTERN, GITHUB_USERNAME_PATTERN
from infrastructure.github_oauth import GitHubOAuthClient, GitHubOAuthUnavailable


class GitHubAccessDenied(APIException):
    status_code = 403
    default_detail = "Không có quyền truy cập GitHub hiện hành."
    default_code = "GITHUB_ACCESS_DENIED"


GitHubForbidden = GitHubAccessDenied


class GitHubAppReauthorizationRequired(APIException):
    status_code = 409
    default_detail = "Hãy cấp quyền GitHub lại."
    default_code = "GITHUB_REAUTH_REQUIRED"


class GitHubNotFound(APIException):
    status_code = 404
    default_detail = "Không tìm thấy installation GitHub có thể truy cập."
    default_code = "GITHUB_NOT_FOUND"


class GitHubRateLimited(APIException):
    status_code = 429
    default_detail = "GitHub đang giới hạn yêu cầu. Hãy thử lại sau."
    default_code = "GITHUB_RATE_LIMITED"

    def __init__(self, retry_after=None, reset_at=None):
        super().__init__()
        self.wait = (
            int(retry_after)
            if isinstance(retry_after, str) and retry_after.isdigit() and len(retry_after) < 6
            else 60
        )
        if (
            retry_after is None
            and isinstance(reset_at, str)
            and reset_at.isdigit()
            and len(reset_at) <= 12
        ):
            self.wait = int(reset_at) - int(timezone.now().timestamp())
        self.wait = min(3600, max(1, self.wait))


@dataclass(frozen=True)
class TokenPair:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True)
class TokenIdentity(TokenPair):
    github_user_id: str
    github_username: str


def github_id(value):
    if type(value) is not int or not re.fullmatch(GITHUB_ID_PATTERN, str(value)):
        raise GitHubOAuthUnavailable()
    return str(value)


def token_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_\-.]{1,8192}", value):
        raise GitHubOAuthUnavailable()
    return value


class GitHubAppClient(GitHubOAuthClient):
    def _configuration(self):
        if not getattr(settings, "INTEGRATION_GITHUB_APP_ENABLED", False):
            raise GitHubOAuthUnavailable()
        app_id = getattr(settings, "INTEGRATION_GITHUB_APP_ID", "")
        slug = getattr(settings, "INTEGRATION_GITHUB_APP_SLUG", "")
        if (
            not isinstance(app_id, str)
            or not re.fullmatch(r"[1-9][0-9]{0,99}", app_id)
            or not isinstance(slug, str)
            or len(slug) > 100
            or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", slug)
        ):
            raise GitHubOAuthUnavailable()
        return super()._configuration()

    def _request_json(self, method, url, *, limit=65_536, empty=False, **kwargs):
        try:
            with requests.request(
                method, url, timeout=(2, 3), allow_redirects=False, stream=True, **kwargs
            ) as response:
                if response.status_code == 401:
                    raise GitHubAppReauthorizationRequired()
                if response.status_code == 403:
                    if response.headers.get("X-RateLimit-Remaining") == "0" or response.headers.get(
                        "Retry-After"
                    ):
                        raise GitHubRateLimited(
                            response.headers.get("Retry-After"),
                            response.headers.get("X-RateLimit-Reset"),
                        )
                    raise GitHubAccessDenied()
                if response.status_code == 404:
                    raise GitHubNotFound()
                if response.status_code == 429:
                    raise GitHubRateLimited(
                        response.headers.get("Retry-After"),
                        response.headers.get("X-RateLimit-Reset"),
                    )
                if empty and response.status_code == 204:
                    return {}
                if response.status_code != 200:
                    raise ValueError()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > limit:
                        raise ValueError()
                payload = json.loads(body)
                if not isinstance(payload, dict) or "error" in payload:
                    raise ValueError()
                return payload
        except (requests.RequestException, ValueError, TypeError, UnicodeError):
            raise GitHubOAuthUnavailable() from None

    def _tokens(self, payload):
        access, refresh = (
            token_value(payload.get("access_token")),
            token_value(payload.get("refresh_token")),
        )
        expires, refresh_expires = (
            payload.get("expires_in"),
            payload.get("refresh_token_expires_in"),
        )
        if (
            str(payload.get("token_type", "")).lower() != "bearer"
            or type(expires) is not int
            or not 1 <= expires <= 86400
            or type(refresh_expires) is not int
            or not expires < refresh_expires <= 366 * 86400
        ):
            raise GitHubOAuthUnavailable()
        now = timezone.now()
        return TokenPair(
            access,
            refresh,
            now + timedelta(seconds=expires),
            now + timedelta(seconds=refresh_expires),
        )

    def _headers(self, token):
        self._configuration()
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token_value(token)}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def exchange(self, *, code, verifier):
        client_id, secret, redirect = self._configuration()
        if (
            not isinstance(code, str)
            or not re.fullmatch(r"[\x21-\x7e]{1,1024}", code)
            or not isinstance(verifier, str)
            or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
        ):
            raise GitHubOAuthUnavailable()
        pair = self._tokens(
            self._request_json(
                "POST",
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": secret,
                    "redirect_uri": redirect,
                    "code": code,
                    "code_verifier": verifier,
                },
            )
        )
        user = self._request_json(
            "GET", "https://api.github.com/user", headers=self._headers(pair.access_token)
        )
        login = user.get("login")
        if (
            not isinstance(login, str)
            or not 1 <= len(login) <= 39
            or not re.fullmatch(GITHUB_USERNAME_PATTERN, login)
        ):
            raise GitHubOAuthUnavailable()
        return TokenIdentity(
            pair.access_token,
            pair.refresh_token,
            pair.expires_at,
            pair.refresh_expires_at,
            github_id(user.get("id")),
            login,
        )

    def refresh(self, *, refresh_token):
        client_id, secret, _ = self._configuration()
        return self._tokens(
            self._request_json(
                "POST",
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": secret,
                    "grant_type": "refresh_token",
                    "refresh_token": token_value(refresh_token),
                },
            )
        )

    def revoke(self, *, access_token):
        # Retirement must drain even when new GitHub App access is disabled.
        client_id, secret, _ = GitHubOAuthClient._configuration(self)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,256}", client_id):
            raise GitHubOAuthUnavailable()
        self._request_json(
            "DELETE",
            f"https://api.github.com/applications/{client_id}/token",
            auth=(client_id, secret),
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            json={"access_token": token_value(access_token)},
            empty=True,
        )

    def _page(self, token, path, key, page, per_page):
        if (
            type(page) is not int
            or not 1 <= page <= 10000
            or type(per_page) is not int
            or not 1 <= per_page <= 100
        ):
            raise GitHubOAuthUnavailable()
        payload = self._request_json(
            "GET",
            "https://api.github.com/" + path,
            headers=self._headers(token),
            params={"page": page, "per_page": per_page},
            limit=1_048_576,
        )
        items, total = payload.get(key), payload.get("total_count")
        if (
            not isinstance(items, list)
            or len(items) > per_page
            or type(total) is not int
            or total < 0
        ):
            raise GitHubOAuthUnavailable()
        return items, page + 1 if page * per_page < total else None

    def installations(self, token, *, page=1, per_page=30):
        items, next_page = self._page(token, "user/installations", "installations", page, per_page)
        result = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("account"), dict):
                raise GitHubOAuthUnavailable()
            account = item["account"]
            if (
                not isinstance(account.get("login"), str)
                or len(account["login"]) > 100
                or account.get("type") not in {"User", "Organization"}
                or item.get("repository_selection") not in {"all", "selected"}
                or item.get("suspended_at") is not None
                and not isinstance(item["suspended_at"], str)
            ):
                raise GitHubOAuthUnavailable()
            result.append(
                {
                    "installation_id": github_id(item.get("id")),
                    "app_id": github_id(item.get("app_id")),
                    "account": {
                        "id": github_id(account.get("id")),
                        "login": account["login"],
                        "type": account["type"],
                    },
                    "repository_selection": item["repository_selection"],
                    "suspended_at": item.get("suspended_at"),
                }
            )
        return {"items": result, "next_page": next_page}

    def repositories(self, token, installation_id, *, page=1, per_page=30):
        if not isinstance(installation_id, str) or not re.fullmatch(
            GITHUB_ID_PATTERN, installation_id
        ):
            raise GitHubOAuthUnavailable()
        items, next_page = self._page(
            token,
            f"user/installations/{installation_id}/repositories",
            "repositories",
            page,
            per_page,
        )
        result = []
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not 1 <= len(item["name"]) <= 100
                or not isinstance(item.get("full_name"), str)
                or not 1 <= len(item["full_name"]) <= 201
                or type(item.get("private")) is not bool
            ):
                raise GitHubOAuthUnavailable()
            result.append(
                {
                    "repository_id": github_id(item.get("id")),
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "private": item["private"],
                }
            )
        return {"items": result, "next_page": next_page}

    def installation_url(self, *, state):
        self._configuration()
        slug = settings.INTEGRATION_GITHUB_APP_SLUG
        setup_uri = getattr(settings, "INTEGRATION_GITHUB_SETUP_URI", "")
        if (
            not isinstance(setup_uri, str)
            or not setup_uri
            or len(setup_uri) > 2048
            or any(ord(char) <= 32 or ord(char) >= 127 for char in setup_uri)
        ):
            raise GitHubOAuthUnavailable()
        try:
            parsed = urlsplit(setup_uri)
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
        return f"https://github.com/apps/{slug}/installations/new?" + urlencode({"state": state})
