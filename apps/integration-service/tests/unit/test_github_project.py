import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.github_app import (
    GitHubAccessDenied,
    GitHubAppClient,
    GitHubAppReauthorizationRequired,
    GitHubNotFound,
    GitHubRateLimited,
)
from infrastructure.github_oauth import GitHubOAuthUnavailable
from infrastructure.github_project import (
    MAX_BODY_BYTES,
    GitHubProjectClient,
    _branch,
    _repository,
    _text,
    _timestamp,
    _url,
)

pytestmark = pytest.mark.unit
SHA = "a" * 40
REPO = {"repo_id": "12", "repo_owner": "octo", "repo_name": "demo"}
DATE = "2026-10-20T00:00:00Z"


@pytest.fixture
def provider(settings):
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_GITHUB_CLIENT_ID = "client-id"
    settings.INTEGRATION_GITHUB_CLIENT_SECRET = "private-secret"
    settings.INTEGRATION_GITHUB_REDIRECT_URI = "https://utask.test/callback"
    settings.INTEGRATION_GITHUB_APP_ID = "42"
    settings.INTEGRATION_GITHUB_APP_SLUG = "utask"
    return GitHubProjectClient()


def response(payload, status=200, headers=None):
    context = MagicMock()
    context.__enter__.return_value.status_code = status
    context.__enter__.return_value.headers = headers or {}
    context.__enter__.return_value.iter_content.return_value = [json.dumps(payload).encode()]
    return context


def metadata(**overrides):
    return {
        "id": 12,
        "owner": {"login": "octo"},
        "name": "demo",
        "default_branch": "main",
        **overrides,
    }


def commit(**overrides):
    return {
        "sha": SHA,
        "commit": {"message": "Fix bug\n\nsecret body", "committer": {"date": DATE}},
        "html_url": f"https://github.com/octo/demo/commit/{SHA}",
        **overrides,
    }


def issue(**overrides):
    return {
        "number": 3,
        "title": "Fix",
        "state": "open",
        "merged_at": None,
        "base": {"repo": {"id": 12}},
        "updated_at": DATE,
        "html_url": "https://github.com/octo/demo/pull/3",
        **overrides,
    }


def test_header_version_is_isolated(provider):
    assert provider._headers("token")["X-GitHub-Api-Version"] == "2026-03-10"
    assert GitHubAppClient()._headers("token")["X-GitHub-Api-Version"] == "2022-11-28"


def test_find_repository_filters_app_and_suspension_and_checks_metadata(provider):
    installation = {"installation_id": "9", "app_id": "42", "suspended_at": None}
    with (
        patch.object(
            provider,
            "installations",
            return_value={
                "items": [
                    installation | {"app_id": "43"},
                    installation | {"suspended_at": DATE},
                    installation,
                ],
                "next_page": None,
            },
        ),
        patch.object(
            provider,
            "repositories",
            return_value={
                "items": [
                    {"repository_id": "12", "name": "demo", "full_name": "octo/demo"},
                ],
                "next_page": None,
            },
        ) as repositories,
        patch.object(provider, "_request_json", return_value=metadata()),
    ):
        assert provider.find_repository("token", "12") == REPO | {
            "installation_id": "9",
            "default_branch": "main",
        }
    repositories.assert_called_once_with("token", "9", page=1, per_page=100)


def test_find_repository_pages_and_exhaustion(provider):
    installation = {"installation_id": "9", "app_id": "42", "suspended_at": None}
    with (
        patch.object(
            provider, "installations", return_value={"items": [installation], "next_page": None}
        ),
        patch.object(
            provider, "repositories", return_value={"items": [], "next_page": 2}
        ) as request,
        pytest.raises(GitHubOAuthUnavailable),
    ):
        provider.find_repository("token", "12")
    assert request.call_count == 29
    with patch.object(provider, "installations", return_value={"items": [], "next_page": None}):
        with pytest.raises(GitHubNotFound):
            provider.find_repository("token", "12")


@pytest.mark.parametrize(
    "payload", [metadata(id=13), metadata(name="renamed"), metadata(owner=None)]
)
def test_metadata_rejects_wrong_repository(provider, payload):
    with patch.object(provider, "_request_json", return_value=payload):
        with pytest.raises((GitHubNotFound, GitHubOAuthUnavailable)):
            provider._metadata("token", "12", owner="octo", name="demo")


def test_metadata_enforces_default_branch_contract_boundary(provider):
    with patch.object(provider, "_request_json", return_value=metadata(default_branch="b" * 100)):
        assert provider._metadata("token", "12")["default_branch"] == "b" * 100
    with patch.object(provider, "_request_json", return_value=metadata(default_branch="b" * 101)):
        with pytest.raises(GitHubOAuthUnavailable):
            provider._metadata("token", "12")


def test_reference_branch_keeps_three_hundred_character_limit(provider):
    branch = "b" * 300
    with patch.object(
        provider,
        "_request_json",
        side_effect=[
            metadata(),
            {"name": branch, "commit": {"sha": SHA}},
        ],
    ):
        result = provider.verify_reference("token", **REPO, link_type="BRANCH", ref_id=branch)
    assert result["ref_id"] == result["title"] == branch


@pytest.mark.parametrize(
    "kind,reference,payload,status",
    [
        ("BRANCH", "feature/fix", {"name": "feature/fix", "commit": {"sha": SHA}}, None),
        ("COMMIT", "aaaaaaa", commit(), None),
        ("PULL_REQUEST", "3", issue(), "OPEN"),
        ("PULL_REQUEST", "3", issue(state="closed", merged_at=DATE), "MERGED"),
        ("PULL_REQUEST", "3", issue(state="closed"), "CLOSED"),
    ],
)
def test_verify_reference_allowlist(provider, kind, reference, payload, status):
    with patch(
        "infrastructure.github_app.requests.request",
        side_effect=[response(metadata()), response(payload)],
    ) as request:
        result = provider.verify_reference("token", **REPO, link_type=kind, ref_id=reference)
    assert result["status"] == status and result["is_verified"] is True
    assert result["ref_id"] == reference
    assert set(result) == {
        "link_type",
        "ref_id",
        "title",
        "status",
        "url",
        "is_verified",
        "synced_at",
    }
    if kind == "BRANCH":
        assert request.call_args.args[1].endswith("branches/feature%2Ffix")


@pytest.mark.parametrize(
    "kind,reference",
    [
        ("OTHER", "main"),
        ("COMMIT", "main"),
        ("PULL_REQUEST", "0"),
        ("BRANCH", "../secret"),
        ("BRANCH", "x?secret"),
    ],
)
def test_verify_invalid_input_does_not_call_provider(provider, kind, reference):
    with patch.object(provider, "_request_json") as request, pytest.raises(GitHubOAuthUnavailable):
        provider.verify_reference("token", **REPO, link_type=kind, ref_id=reference)
    request.assert_not_called()


@pytest.mark.parametrize(
    "kind,reference,payload",
    [
        ("BRANCH", "main", {"name": "other", "commit": {"sha": SHA}}),
        ("COMMIT", "bbbbbbb", commit()),
        ("PULL_REQUEST", "3", issue(number=True)),
        ("PULL_REQUEST", "3", issue(base={"repo": {"id": 99}})),
        ("PULL_REQUEST", "3", issue(state="unknown")),
        ("COMMIT", "aaaaaaa", commit(html_url="https://github.com/other/repo/commit/a")),
    ],
)
def test_verify_rejects_mismatched_facts(provider, kind, reference, payload):
    with patch.object(provider, "_request_json", side_effect=[metadata(), payload]):
        with pytest.raises(GitHubOAuthUnavailable):
            provider.verify_reference("token", **REPO, link_type=kind, ref_id=reference)


def test_activity_allowlists_and_filters_issues(provider):
    with patch(
        "infrastructure.github_project.requests.request",
        side_effect=[
            response(metadata()),
            response([commit()]),
            response([issue()]),
            response(
                [issue(pull_request={}), issue(html_url="https://github.com/octo/demo/issues/3")]
            ),
        ],
    ) as request:
        result = provider.activity("token", **REPO)
    assert result["partial"] is False
    assert all(len(result[key]) == 1 for key in ("commits", "pull_requests", "issues"))
    assert result["commits"][0]["title"] == "Fix bug"
    assert set(result["commits"][0]) == {"id", "title", "status", "url", "occurred_at"}
    for call in request.call_args_list:
        assert call.kwargs["timeout"] == (2, 3)
        assert call.kwargs["allow_redirects"] is False and call.kwargs["stream"] is True
        assert call.kwargs["headers"]["X-GitHub-Api-Version"] == "2026-03-10"


@pytest.mark.parametrize("denied", [0, 1, 2])
def test_activity_optional_permission_denied_is_partial(provider, denied):
    payloads = [response([]) for _ in range(3)]
    payloads[denied] = response({"private": "secret"}, 403)
    with patch(
        "infrastructure.github_project.requests.request",
        side_effect=[response(metadata()), *payloads],
    ):
        result = provider.activity("token", **REPO)
    assert result == {"commits": [], "pull_requests": [], "issues": [], "partial": True}


@pytest.mark.parametrize(
    "status,headers,error",
    [
        (401, {}, GitHubAppReauthorizationRequired),
        (403, {}, GitHubAccessDenied),
        (403, {"X-RateLimit-Remaining": "0"}, GitHubRateLimited),
        (404, {}, GitHubNotFound),
        (429, {}, GitHubRateLimited),
        (302, {}, GitHubOAuthUnavailable),
        (500, {}, GitHubOAuthUnavailable),
    ],
)
def test_array_http_errors(provider, status, headers, error):
    with patch(
        "infrastructure.github_project.requests.request", return_value=response({}, status, headers)
    ):
        with pytest.raises(error):
            provider._array("token", "repos/octo/demo/commits", params={"per_page": 20})


@pytest.mark.parametrize("payload", [{}, [None], [{}] * 21])
def test_array_requires_bounded_objects(provider, payload):
    with patch("infrastructure.github_project.requests.request", return_value=response(payload)):
        with pytest.raises(GitHubOAuthUnavailable):
            provider._array("token", "repos/octo/demo/commits", params={})


def test_array_body_limit_invalid_json_and_transport(provider):
    for chunks in ([b"x" * (MAX_BODY_BYTES + 1)], [b"bad-json"], [b"\xff"]):
        reply = response([])
        reply.__enter__.return_value.iter_content.return_value = chunks
        with patch("infrastructure.github_project.requests.request", return_value=reply):
            with pytest.raises(GitHubOAuthUnavailable):
                provider._array("token", "repos/octo/demo/commits", params={})
    with patch(
        "infrastructure.github_project.requests.request", side_effect=requests.Timeout("secret")
    ):
        with pytest.raises(GitHubOAuthUnavailable) as caught:
            provider._array("token", "repos/octo/demo/commits", params={})
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("endpoint", ["array", "metadata", "reference"])
def test_deep_json_maps_recursion_error_to_provider_unavailable(provider, endpoint):
    deep = b"[" * 2000 + b"0" + b"]" * 2000
    if endpoint != "array":
        deep = b'{"nested":' + deep + b"}"
    reply = response([])
    reply.__enter__.return_value.iter_content.return_value = [deep]
    responses = [response(metadata()), reply] if endpoint == "reference" else [reply]
    with patch("infrastructure.github_project.requests.request", side_effect=responses):
        with pytest.raises(GitHubOAuthUnavailable) as caught:
            if endpoint == "array":
                provider._array("token", "repos/octo/demo/commits", params={})
            elif endpoint == "metadata":
                provider._metadata("token", "12")
            else:
                provider.verify_reference("token", **REPO, link_type="BRANCH", ref_id="main")
    assert caught.value.status_code == 503


@pytest.mark.parametrize(
    "value,expected",
    [
        (DATE, "2026-10-20T00:00:00+00:00"),
        ("2026-10-20 01:02:03+07:00", "2026-10-20T01:02:03+07:00"),
        ("2026-10-20T01:02:03.123Z", "2026-10-20T01:02:03.123000+00:00"),
    ],
)
def test_timestamp_normalizes_rfc3339_output(value, expected):
    assert _timestamp(value) == expected


def test_timestamp_rejects_timezone_seconds_not_supported_by_rfc3339():
    with pytest.raises(GitHubOAuthUnavailable):
        _timestamp("2026-10-20T00:00:00+00:00:01")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/octo/demo/a",
        "https://user@github.com/octo/demo/a",
        "https://github.com:443/octo/demo/a",
        "https://github.com/octo/demo/a?q=token",
        "https://github.com/octo/demo/a#x",
        "https://evil.test/octo/demo/a",
        "https://github.com/octo/demo/a?",
        "https://github.com/octo/demo/a#",
        "https://[invalid/octo/demo/a",
    ],
)
def test_url_rejects_unsafe_origin_and_extras(url):
    with pytest.raises(GitHubOAuthUnavailable):
        _url(url, "octo", "demo")


@pytest.mark.parametrize(
    "function,args",
    [
        (_text, (None, 10)),
        (_text, ("x\n", 10)),
        (_text, ("", 10)),
        (_repository, ("0", "octo", "demo")),
        (_repository, ("12", "octo", "..")),
        (_repository, ("12", "bad/owner", "demo")),
        (_branch, ("x.lock",)),
        (_branch, ("a//b",)),
        (_branch, ("a@{b",)),
        (_timestamp, ("bad",)),
        (_timestamp, ("2026-01-01",)),
        (GitHubProjectClient._sha, (True,)),
        (GitHubProjectClient._commit_title, ({"commit": {}},)),
        (GitHubProjectClient._issue_fields, ({"title": "Fix", "state": "unknown"},)),
        (GitHubProjectClient._issue_fields, ({"title": "Fix", "state": []},)),
    ],
)
def test_validation_helpers_reject_malformed_facts(function, args):
    with pytest.raises(GitHubOAuthUnavailable):
        function(*args)


def test_activity_rejects_malformed_timestamp_and_committer(provider):
    for payload in (
        commit(commit={"message": "Fix", "committer": None}),
        commit(commit={"message": "Fix", "committer": {"date": "bad"}}),
    ):
        with patch(
            "infrastructure.github_project.requests.request",
            side_effect=[response(metadata()), response([payload])],
        ):
            with pytest.raises(GitHubOAuthUnavailable):
                provider.activity("token", **REPO)


def test_activity_accepts_exactly_twenty_items(provider):
    with patch(
        "infrastructure.github_project.requests.request",
        side_effect=[response(metadata()), response([commit()] * 20), response([]), response([])],
    ):
        assert len(provider.activity("token", **REPO)["commits"]) == 20


def test_find_repository_checks_discovery_name_and_paginates(provider):
    installation = {"installation_id": "9", "app_id": "42", "suspended_at": None}
    repository = {"repository_id": "12", "name": "demo", "full_name": "octo/demo"}
    with (
        patch.object(
            provider,
            "installations",
            side_effect=[
                {"items": [], "next_page": 2},
                {"items": [installation], "next_page": None},
            ],
        ),
        patch.object(
            provider,
            "repositories",
            side_effect=[
                {"items": [], "next_page": 2},
                {"items": [repository], "next_page": None},
            ],
        ),
        patch.object(provider, "_request_json", return_value=metadata()),
    ):
        assert provider.find_repository("token", "12")["installation_id"] == "9"
    with (
        patch.object(
            provider, "installations", return_value={"items": [installation], "next_page": None}
        ),
        patch.object(
            provider,
            "repositories",
            return_value={
                "items": [repository | {"full_name": "octo/old"}],
                "next_page": None,
            },
        ),
        patch.object(provider, "_request_json", return_value=metadata()),
        pytest.raises(GitHubNotFound),
    ):
        provider.find_repository("token", "12")


@pytest.mark.parametrize("repo_id", [None, True, "0", "12/../13"])
def test_find_repository_rejects_invalid_id_before_network(provider, repo_id):
    with patch.object(provider, "installations") as request, pytest.raises(GitHubOAuthUnavailable):
        provider.find_repository("token", repo_id)
    request.assert_not_called()
