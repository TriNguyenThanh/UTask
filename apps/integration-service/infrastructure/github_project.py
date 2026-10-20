"""Bounded, allowlisted GitHub facts for Project connections (ADR-005)."""

import json
import re
from datetime import datetime
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings
from django.utils import timezone

from apps.github_accounts.validation import GITHUB_ID_PATTERN, GITHUB_USERNAME_PATTERN
from infrastructure.github_app import (
    GitHubAccessDenied,
    GitHubAppClient,
    GitHubAppReauthorizationRequired,
    GitHubNotFound,
    GitHubRateLimited,
    github_id,
)
from infrastructure.github_oauth import GitHubOAuthUnavailable

API_VERSION = "2026-03-10"
MAX_DISCOVERY_PAGES = 30
MAX_BODY_BYTES = 1_048_576


def _text(value, limit):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise GitHubOAuthUnavailable()
    return value


def _repository(repo_id, owner, name):
    if not isinstance(repo_id, str) or not re.fullmatch(GITHUB_ID_PATTERN, repo_id):
        raise GitHubOAuthUnavailable()
    if (
        not re.fullmatch(GITHUB_USERNAME_PATTERN, _text(owner, 39))
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", _text(name, 100))
        or name in {".", ".."}
    ):
        raise GitHubOAuthUnavailable()
    return f"repos/{quote(owner, safe='')}/{quote(name, safe='')}"


def _branch(value):
    value = _text(value, 300)
    if (
        any(char in value for char in " ~^:?*[\\")
        or ".." in value
        or "@{" in value
        or value == "@"
        or any(
            not part or part.startswith(".") or part.endswith((".", ".lock"))
            for part in value.split("/")
        )
    ):
        raise GitHubOAuthUnavailable()
    return value


def _url(value, owner, name):
    value = _text(value, 1000)
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise GitHubOAuthUnavailable() from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or "\\" in value
        or not parsed.path.startswith(f"/{owner}/{name}/")
    ):
        raise GitHubOAuthUnavailable()
    return value


def _timestamp(value):
    value = _text(value, 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() % 60:
            raise ValueError()
    except ValueError:
        raise GitHubOAuthUnavailable() from None
    return parsed.isoformat()


class GitHubProjectClient(GitHubAppClient):
    def _headers(self, token):
        return super()._headers(token) | {"X-GitHub-Api-Version": API_VERSION}

    def _request_json(self, *args, **kwargs):
        try:
            return super()._request_json(*args, **kwargs)
        except RecursionError:
            raise GitHubOAuthUnavailable() from None

    def _array(self, token, path, *, params):
        """Read one bounded JSON array; never follow provider pagination URLs."""
        try:
            with requests.request(
                "GET",
                "https://api.github.com/" + path,
                headers=self._headers(token),
                params=params,
                timeout=(2, 3),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code == 401:
                    raise GitHubAppReauthorizationRequired()
                if response.status_code in {403, 429}:
                    if (
                        response.status_code == 429
                        or response.headers.get("X-RateLimit-Remaining") == "0"
                        or response.headers.get("Retry-After")
                    ):
                        raise GitHubRateLimited(
                            response.headers.get("Retry-After"),
                            response.headers.get("X-RateLimit-Reset"),
                        )
                    raise GitHubAccessDenied()
                if response.status_code == 404:
                    raise GitHubNotFound()
                if response.status_code != 200:
                    raise ValueError()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        raise ValueError()
                payload = json.loads(body)
                if (
                    not isinstance(payload, list)
                    or len(payload) > 20
                    or any(not isinstance(item, dict) for item in payload)
                ):
                    raise ValueError()
                return payload
        except (requests.RequestException, ValueError, TypeError, UnicodeError, RecursionError):
            raise GitHubOAuthUnavailable() from None

    def _metadata(self, token, repo_id, *, owner=None, name=None):
        if not isinstance(repo_id, str) or not re.fullmatch(GITHUB_ID_PATTERN, repo_id):
            raise GitHubOAuthUnavailable()
        payload = self._request_json(
            "GET",
            f"https://api.github.com/repositories/{repo_id}",
            headers=self._headers(token),
            limit=MAX_BODY_BYTES,
        )
        repo_owner = payload.get("owner")
        if not isinstance(repo_owner, dict):
            raise GitHubOAuthUnavailable()
        actual_owner, actual_name = repo_owner.get("login"), payload.get("name")
        _repository(github_id(payload.get("id")), actual_owner, actual_name)
        if str(payload["id"]) != repo_id or (
            owner is not None and (actual_owner != owner or actual_name != name)
        ):
            raise GitHubNotFound()
        return {
            "repo_id": repo_id,
            "repo_owner": actual_owner,
            "repo_name": actual_name,
            "default_branch": _branch(_text(payload.get("default_branch"), 100)),
        }

    def find_repository(self, token, repository_id):
        if not isinstance(repository_id, str) or not re.fullmatch(GITHUB_ID_PATTERN, repository_id):
            raise GitHubOAuthUnavailable()
        page, budget = 1, MAX_DISCOVERY_PAGES
        while page is not None and budget:
            installations = self.installations(token, page=page, per_page=100)
            budget -= 1
            for installation in installations["items"]:
                if installation["app_id"] != settings.INTEGRATION_GITHUB_APP_ID or (
                    installation["suspended_at"] is not None
                ):
                    continue
                repo_page = 1
                while repo_page is not None:
                    if not budget:
                        raise GitHubOAuthUnavailable()
                    repositories = self.repositories(
                        token, installation["installation_id"], page=repo_page, per_page=100
                    )
                    budget -= 1
                    for repo in repositories["items"]:
                        if repo["repository_id"] == repository_id:
                            metadata = self._metadata(token, repository_id)
                            if (
                                repo["full_name"]
                                != (f"{metadata['repo_owner']}/{metadata['repo_name']}")
                                or repo["name"] != metadata["repo_name"]
                            ):
                                raise GitHubNotFound()
                            return {"installation_id": installation["installation_id"], **metadata}
                    repo_page = repositories["next_page"]
            page = installations["next_page"]
        if page is not None:
            raise GitHubOAuthUnavailable()
        raise GitHubNotFound()

    def verify_reference(self, token, *, repo_id, repo_owner, repo_name, link_type, ref_id):
        path = _repository(repo_id, repo_owner, repo_name)
        _text(ref_id, 300)
        if link_type == "BRANCH":
            endpoint = "branches/" + quote(_branch(ref_id), safe="")
        elif link_type == "COMMIT" and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref_id):
            endpoint = "commits/" + ref_id
        elif link_type == "PULL_REQUEST" and re.fullmatch(r"[1-9][0-9]{0,19}", ref_id):
            endpoint = "pulls/" + ref_id
        else:
            raise GitHubOAuthUnavailable()
        self._metadata(token, repo_id, owner=repo_owner, name=repo_name)
        payload = self._request_json(
            "GET",
            f"https://api.github.com/{path}/{endpoint}",
            headers=self._headers(token),
            limit=MAX_BODY_BYTES,
        )
        status = None
        if link_type == "BRANCH":
            if payload.get("name") != ref_id or not isinstance(payload.get("commit"), dict):
                raise GitHubOAuthUnavailable()
            self._sha(payload["commit"].get("sha"))
            title, url = (
                ref_id,
                f"https://github.com/{repo_owner}/{repo_name}/tree/{quote(ref_id, safe='')}",
            )
        elif link_type == "COMMIT":
            sha = self._sha(payload.get("sha"))
            if not sha.lower().startswith(ref_id.lower()):
                raise GitHubOAuthUnavailable()
            title, url = self._commit_title(payload), payload.get("html_url")
        else:
            if type(payload.get("number")) is not int or str(payload["number"]) != ref_id:
                raise GitHubOAuthUnavailable()
            base = payload.get("base")
            if (
                not isinstance(base, dict)
                or not isinstance(base.get("repo"), dict)
                or (github_id(base["repo"].get("id")) != repo_id)
            ):
                raise GitHubOAuthUnavailable()
            title, status = self._issue_fields(payload, pull_request=True)
            url = payload.get("html_url")
        return {
            "link_type": link_type,
            "ref_id": ref_id,
            "title": title,
            "status": status,
            "url": _url(url, repo_owner, repo_name),
            "is_verified": True,
            "synced_at": timezone.now().isoformat(),
        }

    @staticmethod
    def _sha(value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
            raise GitHubOAuthUnavailable()
        return value

    @staticmethod
    def _commit_title(payload):
        commit = payload.get("commit")
        if (
            not isinstance(commit, dict)
            or not isinstance(commit.get("message"), str)
            or (not 1 <= len(commit["message"]) <= MAX_BODY_BYTES)
        ):
            raise GitHubOAuthUnavailable()
        return _text(commit["message"].split("\n")[0][:300], 300)

    @staticmethod
    def _issue_fields(payload, *, pull_request=False):
        title = _text(payload.get("title"), 65536)[:300]
        state = payload.get("state")
        if not isinstance(state, str) or state not in {"open", "closed"}:
            raise GitHubOAuthUnavailable()
        if pull_request and payload.get("merged_at") is not None:
            _timestamp(payload["merged_at"])
            return title, "MERGED"
        return title, state.upper()

    def activity(self, token, *, repo_id, repo_owner, repo_name):
        path = _repository(repo_id, repo_owner, repo_name)
        self._metadata(token, repo_id, owner=repo_owner, name=repo_name)
        result = {"commits": [], "pull_requests": [], "issues": [], "partial": False}
        for key, endpoint in (
            ("commits", "commits"),
            ("pull_requests", "pulls"),
            ("issues", "issues"),
        ):
            params = {"per_page": 20, "page": 1}
            if key != "commits":
                params.update(state="all", sort="updated", direction="desc")
            try:
                items = self._array(token, f"{path}/{endpoint}", params=params)
            except GitHubAccessDenied:
                result["partial"] = True
                continue
            for item in items:
                if key == "issues" and "pull_request" in item:
                    continue
                if key == "commits":
                    identifier = self._sha(item.get("sha"))
                    title, status = self._commit_title(item), None
                    committer = item["commit"].get("committer")
                    if not isinstance(committer, dict):
                        raise GitHubOAuthUnavailable()
                    occurred = committer.get("date")
                else:
                    identifier = github_id(item.get("number"))
                    title, status = self._issue_fields(item, pull_request=key == "pull_requests")
                    occurred = item.get("updated_at")
                result[key].append(
                    {
                        "id": identifier,
                        "title": title,
                        "status": status,
                        "url": _url(item.get("html_url"), repo_owner, repo_name),
                        "occurred_at": _timestamp(occurred),
                    }
                )
        return result
