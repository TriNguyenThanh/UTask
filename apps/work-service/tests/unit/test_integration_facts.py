from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common.errors import WorkError
from infrastructure.integration import AccountFact, ConnectionFact, ReferenceFact

pytestmark = pytest.mark.unit


@pytest.fixture
def connection_fact():
    return ConnectionFact(
        uuid4(),
        "operation-1",
        1,
        1,
        "CONNECTED",
        "repo-1",
        "team",
        "team/repo",
        "main",
        datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"generation": True},
        {"source_version": -1},
        {"project_id": "not-uuid"},
        {"status": "READY"},
        {"operation_id": ""},
        {"operation_id": "x" * 101},
        {"synced_at": datetime(2026, 1, 1)},
        {"repo_id": None},
        {"repo_owner": 7},
        {"repo_name": "x" * 256},
        {"default_branch": ""},
    ],
)
def test_connection_fact_invalid_binding_version_or_metadata_is_rejected(connection_fact, change):
    with pytest.raises(WorkError) as error:
        replace(connection_fact, **change).validate()
    assert error.value.code == "INTEGRATION_UNAVAILABLE" and error.value.status_code == 503


@pytest.mark.parametrize("status", ["PENDING", "DISCONNECTED"])
def test_connection_without_repository_metadata_is_valid_only_when_not_connected(
    connection_fact, status
):
    fact = replace(
        connection_fact,
        status=status,
        repo_id=None,
        repo_owner=None,
        repo_name=None,
        default_branch=None,
    )
    assert fact.validate() is fact


@pytest.fixture
def reference_fact(connection_fact):
    return ReferenceFact(
        connection_fact.project_id,
        "repo-1",
        1,
        1,
        "PULL_REQUEST",
        "24",
        "Title",
        "OPEN",
        "https://github.com/team/repo/pull/24",
        True,
        datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"generation": -1},
        {"source_version": False},
        {"project_id": "wrong"},
        {"repo_id": ""},
        {"repo_id": "x" * 101},
        {"link_type": "ISSUE"},
        {"ref_id": ""},
        {"ref_id": "x" * 301},
        {"is_verified": False},
        {"synced_at": None},
        {"title": 7},
        {"title": "x" * 301},
        {"status": "DONE"},
        {"ref_id": "01"},
        {"ref_id": "0"},
        {"ref_id": "１２"},
        {"url": "http://github.com/team/repo"},
        {"url": "https://other.test/team/repo"},
        {"url": "https://user@github.com/team/repo"},
        {"url": "https://github.com/team/repo?ref=1"},
        {"url": "https://github.com/" + "x" * 1001},
    ],
)
def test_reference_fact_requires_canonical_verified_source(reference_fact, change):
    with pytest.raises(WorkError) as error:
        replace(reference_fact, **change).validate()
    assert error.value.code == "INTEGRATION_UNAVAILABLE"


@pytest.mark.parametrize("kind,ref", [("BRANCH", "feature/work"), ("COMMIT", "abc123")])
def test_non_pr_reference_allows_named_ref_but_rejects_pr_status(reference_fact, kind, ref):
    fact = replace(reference_fact, link_type=kind, ref_id=ref, status=None, url=None, title=None)
    assert fact.validate() is fact
    with pytest.raises(WorkError):
        replace(fact, status="MERGED").validate()


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": "invalid"},
        {"source_version": True},
        {"verified": 1},
        {"github_user_id": ""},
        {"github_username": "x" * 101},
    ],
)
def test_account_fact_rejects_invalid_identity_version_and_metadata(change):
    fact = AccountFact(uuid4(), "gh-1", "username", 1, True)
    with pytest.raises(WorkError) as error:
        replace(fact, **change).validate()
    assert error.value.code == "INTEGRATION_UNAVAILABLE"
