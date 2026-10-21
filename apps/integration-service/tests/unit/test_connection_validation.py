from copy import deepcopy
from uuid import UUID

import pytest
from rest_framework.exceptions import ParseError

from apps.github_connections import validation

pytestmark = pytest.mark.unit
ACTOR = UUID("11111111-1111-4111-8111-111111111111")
PREPARE = {
    "operation_id": "operation:1",
    "action": "CONNECT",
    "expected_generation": 0,
    "github_repo_id": "42",
}


def test_project_and_digest_are_canonical():
    assert validation.project_uuid(str(ACTOR)) == ACTOR
    assert validation.payload_digest(PREPARE, ACTOR) == validation.payload_digest(
        dict(reversed(list(PREPARE.items()))), str(ACTOR)
    )
    assert validation.payload_digest(PREPARE, ACTOR) != validation.payload_digest(
        {**PREPARE, "github_repo_id": "43"}, ACTOR
    )
    assert len(validation.payload_digest(PREPARE, ACTOR)) == 64


@pytest.mark.parametrize("value", [None, True, 1, "", "bad", UUID(int=0)])
def test_project_rejects_invalid_ids(value):
    with pytest.raises(ParseError):
        validation.project_uuid(value)


@pytest.mark.parametrize("value", [None, "", ".", "..", "bad/path", "with space", "x" * 101, 1])
def test_operation_rejects_invalid_ids(value):
    with pytest.raises(ParseError):
        validation.operation_id(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_generation", True),
        ("expected_generation", -1),
        ("expected_generation", 2**63),
        ("expected_generation", "1"),
        ("github_repo_id", "0"),
        ("github_repo_id", "01"),
        ("github_repo_id", 42),
        ("github_repo_id", None),
        ("action", "OTHER"),
        ("action", []),
        ("unexpected", "secret"),
    ],
)
def test_prepare_rejects_malformed_command(field, value):
    with pytest.raises(ParseError):
        validation.prepare_payload({**PREPARE, field: value})


def test_prepare_disconnect_and_command_validation():
    assert validation.prepare_payload(PREPARE) == PREPARE
    body = {**PREPARE, "action": "DISCONNECT", "github_repo_id": None}
    assert validation.prepare_payload(body) == body
    with pytest.raises(ParseError):
        validation.prepare_payload({**body, "github_repo_id": "42"})
    assert validation.command_payload({"operation_id": "x", "generation": 1})
    for body in [
        None,
        {},
        {"operation_id": "x", "generation": 0},
        {"operation_id": "x", "generation": True},
        {"operation_id": "x", "generation": 1, "actor_id": "fake"},
    ]:
        with pytest.raises(ParseError):
            validation.command_payload(body)


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 0),
        ("repo_id", "01"),
        ("link_type", "ISSUE"),
        ("link_type", "COMMIT"),
        ("link_type", []),
        ("ref_id", ""),
        ("ref_id", "x" * 301),
        ("ref_id", "main\n"),
        ("ref_id", "main\x7f"),
        ("access_token", "secret"),
    ],
)
def test_reference_rejects_malformed_input(field, value):
    body = {"repo_id": "42", "generation": 1, "link_type": "BRANCH", "ref_id": "main"}
    assert validation.reference_payload(body) == body
    body = deepcopy(body)
    body[field] = value
    with pytest.raises(ParseError):
        validation.reference_payload(body)


@pytest.mark.parametrize(
    "ref,valid",
    [
        ("a" * 6, False),
        ("a" * 7, True),
        ("A" * 40, True),
        ("a" * 41, False),
        ("not-a-sha", False),
        ("１２３４５６７", False),
    ],
)
def test_commit_reference_boundaries(ref, valid):
    body = {"repo_id": "42", "generation": 1, "link_type": "COMMIT", "ref_id": ref}
    if valid:
        assert validation.reference_payload(body) == body
    else:
        with pytest.raises(ParseError):
            validation.reference_payload(body)
