import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.messaging.consumer import PoisonEvent
from apps.messaging.integration_consumer import validate_account_event, validate_reference_event
from common.errors import WorkError
from infrastructure.integration import (
    RemoteIntegration,
    account_fact_from_data,
    project_activity_from_data,
    reference_event_from_data,
)

pytestmark = pytest.mark.unit

PROJECT_ID = uuid4()
USER_ID = uuid4()
STAMP = "2026-11-24T12:00:00Z"
SHA40 = "0123456789abcdef0123456789abcdef01234567"


def _account_payload(**overrides):
    data = {
        "user_id": str(USER_ID),
        "github_user_id": "12345678",
        "github_username": "student-dev",
        "source_version": 2,
        "verified": True,
        "synced_at": STAMP,
    }
    data.update(overrides)
    return data


def _reference_payload(**overrides):
    data = {
        "project_id": str(PROJECT_ID),
        "repo_id": "12345",
        "generation": 1,
        "source_version": 3,
        "task_code": "UTASK-12",
        "link_type": "PULL_REQUEST",
        "ref_id": "42",
        "title": "Fix UTASK-12 auth middleware",
        "status": "OPEN",
        "url": "https://github.com/student-dev/utask-demo/pull/42",
        "is_verified": True,
        "synced_at": STAMP,
    }
    data.update(overrides)
    return data


def _activity_payload(**overrides):
    data = {
        "project_id": str(PROJECT_ID),
        "repo_id": "12345",
        "repo_owner": "student-dev",
        "repo_name": "utask-demo",
        "default_branch": "main",
        "generation": 1,
        "status": "CONNECTED",
        "open_pull_requests_count": 1,
        "branches": [
            {
                "name": "main",
                "sha": SHA40,
                "url": "https://github.com/student-dev/utask-demo/tree/main",
            }
        ],
        "commits": [
            {
                "id": SHA40,
                "title": "feat: add UTASK-12",
                "url": f"https://github.com/student-dev/utask-demo/commit/{SHA40}",
                "occurred_at": STAMP,
            }
        ],
        "pull_requests": [
            {
                "id": "42",
                "title": "Fix UTASK-12",
                "status": "OPEN",
                "url": "https://github.com/student-dev/utask-demo/pull/42",
                "occurred_at": STAMP,
            }
        ],
        "issues": [
            {
                "id": "15",
                "title": "Improve logging",
                "status": "OPEN",
                "url": "https://github.com/student-dev/utask-demo/issues/15",
                "occurred_at": STAMP,
            }
        ],
        "synced_at": STAMP,
    }
    data.update(overrides)
    return data


def _envelope(event_type, aggregate_id, payload, **overrides):
    body = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "aggregate_id": str(aggregate_id),
        "occurred_at": STAMP,
        "trace_id": str(uuid4()),
        "producer": "integration-service",
        "payload": payload,
    }
    body.update(overrides)
    return body


def test_account_event_parser_accepts_valid_and_rejects_invalid():
    fact = account_fact_from_data(_account_payload())
    assert fact.user_id == USER_ID and fact.verified is True and fact.source_version == 2
    unlinked = account_fact_from_data(_account_payload(verified=False, source_version=3))
    assert unlinked.verified is False

    event = _envelope("integration.github.account.changed", USER_ID, _account_payload())
    assert validate_account_event(event).github_user_id == "12345678"

    for bad_payload in (
        {"extra": 1},
        {"source_version": 0},
        {"source_version": True},
        {"github_user_id": "abc"},
        {"github_user_id": ""},
        {"github_username": ""},
        {"verified": 1},
        {"synced_at": "2026-11-24T12:00:00"},
        {"user_id": "not-uuid"},
    ):
        with pytest.raises(WorkError):
            account_fact_from_data(_account_payload(**bad_payload))

    for bad_envelope in (
        {"producer": "identity-service"},
        {"event_version": 2},
        {"aggregate_id": str(uuid4())},
        {"occurred_at": "2026-11-24T12:00:00"},
    ):
        with pytest.raises(PoisonEvent):
            validate_account_event(event | bad_envelope)


def test_reference_event_parser_accepts_valid_and_rejects_invalid():
    task_code, pr_fact = reference_event_from_data(_reference_payload())
    assert (
        task_code == "UTASK-12" and pr_fact.link_type == "PULL_REQUEST" and pr_fact.ref_id == "42"
    )

    branch_code, branch_fact = reference_event_from_data(
        _reference_payload(
            task_code="26UT-5",
            link_type="BRANCH",
            ref_id="feat/26UT-5-login",
            status=None,
            url="https://github.com/student-dev/utask-demo/tree/feat/26UT-5-login",
        )
    )
    assert branch_code == "26UT-5" and branch_fact.status is None

    commit_code, commit_fact = reference_event_from_data(
        _reference_payload(
            link_type="COMMIT",
            ref_id=SHA40,
            status=None,
            url=f"https://github.com/student-dev/utask-demo/commit/{SHA40}",
        )
    )
    assert commit_code == "UTASK-12" and commit_fact.link_type == "COMMIT"

    event = _envelope("integration.github.reference.detected", PROJECT_ID, _reference_payload())
    assert validate_reference_event(event)[0] == "UTASK-12"

    for bad_payload in (
        {"extra": 1},
        {"task_code": "utask-12"},
        {"task_code": "UT-0"},
        {"task_code": "A-1"},
        {"repo_id": "not-numeric"},
        {"generation": 0},
        {"source_version": 0},
        {"is_verified": False},
        {"link_type": "COMMIT", "ref_id": SHA40, "status": "OPEN"},
        {"link_type": "PULL_REQUEST", "ref_id": "#42"},
        {"url": "http://github.com/student-dev/utask-demo/pull/42"},
        {"url": "https://evil.example/student-dev/utask-demo/pull/42"},
        {"url": "https://github.com/student-dev/utask-demo/pull/42?x=1"},
        {"url": "https://github.com/student-dev/utask-demo/pull/42#top"},
        {"synced_at": "2026-11-24T12:00:00"},
    ):
        with pytest.raises(WorkError):
            reference_event_from_data(_reference_payload(**bad_payload))

    with pytest.raises(PoisonEvent):
        validate_reference_event(event | {"aggregate_id": str(uuid4())})


def test_project_activity_parser_accepts_valid_and_rejects_invalid():
    for status in ("CONNECTED", "PARTIAL", "STALE", "REAUTH_REQUIRED"):
        parsed = project_activity_from_data(_activity_payload(status=status), PROJECT_ID)
        assert parsed["status"] == status
        assert parsed["connection_generation"] == 1
        assert len(parsed["branches"]) == 1
        assert len(parsed["commits"]) == 1
        assert len(parsed["pull_requests"]) == 1
        assert len(parsed["issues"]) == 1

    for bad_payload in (
        {"extra": 1},
        {"project_id": str(uuid4())},
        {"status": "DISCONNECTED"},
        {"generation": 0},
        {"generation": True},
        {"open_pull_requests_count": -1},
        {"open_pull_requests_count": False},
        {
            "branches": [
                {"name": "main", "sha": "bad-sha", "url": "https://github.com/a/b/tree/main"}
            ]
        },
        {
            "branches": [
                {"name": f"b-{i}", "sha": SHA40, "url": "https://github.com/a/b/tree/x"}
                for i in range(21)
            ]
        },
        {
            "commits": [
                {"id": SHA40, "title": "t", "url": "https://evil.test/c", "occurred_at": STAMP}
            ]
        },
        {
            "pull_requests": [
                {
                    "id": "42",
                    "title": "t",
                    "status": "DRAFT",
                    "url": "https://github.com/a/b/pull/42",
                    "occurred_at": STAMP,
                }
            ]
        },
        {
            "issues": [
                {
                    "id": "15",
                    "title": "t",
                    "status": "MERGED",
                    "url": "https://github.com/a/b/issues/15",
                    "occurred_at": STAMP,
                }
            ]
        },
        {"synced_at": "2026-11-24T12:00:00"},
    ):
        with pytest.raises(WorkError):
            project_activity_from_data(_activity_payload(**bad_payload), PROJECT_ID)


def test_remote_integration_fetch_project_activity_headers_and_oversize_guard(
    settings, monkeypatch
):
    settings.WORK_INTEGRATION_BASE_URL = "http://integration.test"
    settings.WORK_INTEGRATION_SERVICE_KEY = "w" * 32
    reply = MagicMock()
    reply.status_code = 200
    payload = _activity_payload()
    reply.iter_content.return_value = [json.dumps({"success": True, "data": payload}).encode()]
    request = MagicMock()
    request.return_value.__enter__.return_value = reply
    monkeypatch.setattr("infrastructure.integration.requests.request", request)

    result = RemoteIntegration().fetch_project_activity(
        project_id=PROJECT_ID, bearer="Bearer actor-jwt"
    )
    assert result["project_id"] == str(PROJECT_ID)
    assert result["connection_generation"] == 1
    assert request.call_args.args == (
        "GET",
        f"http://integration.test/api/v1/internal/projects/{PROJECT_ID}/github/activity",
    )
    assert request.call_args.kwargs["headers"] == {
        "X-Service-Key": "w" * 32,
        "Accept": "application/json",
        "Authorization": "Bearer actor-jwt",
    }

    # Accepts payloads between 64 KiB and 128 KiB, rejects payloads > 128 KiB.
    large_commits = [
        {
            "id": SHA40,
            "title": "A" * 290,
            "url": f"https://github.com/student-dev/utask-demo/commit/{SHA40}",
            "occurred_at": STAMP,
        }
        for _ in range(20)
    ]
    padded = json.dumps(
        {"success": True, "data": _activity_payload(commits=large_commits)}
    ).encode()
    padded = padded + (b" " * (70_000 - len(padded)))
    reply.iter_content.return_value = [padded]
    assert (
        RemoteIntegration().fetch_project_activity(
            project_id=PROJECT_ID, bearer="Bearer actor-jwt"
        )["status"]
        == "CONNECTED"
    )

    reply.iter_content.return_value = [b"x" * 131_073]
    with pytest.raises(WorkError) as captured:
        RemoteIntegration().fetch_project_activity(project_id=PROJECT_ID, bearer="Bearer actor-jwt")
    assert captured.value.status_code == 503
