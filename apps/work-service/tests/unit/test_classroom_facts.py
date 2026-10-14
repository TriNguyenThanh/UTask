from dataclasses import replace
from uuid import uuid4

import pytest

from common.errors import WorkError
from infrastructure.classroom import GroupMemberFact, GroupSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        "empty-group",
        "empty-class",
        "bool-version",
        "negative-version",
        "duplicate-member",
        "invalid-role",
        "invalid-status",
        "invalid-user",
        "no-leader",
        "two-leaders",
    ],
)
def test_group_snapshot_rejects_ambiguous_or_invalid_authority(invalid):
    user = uuid4()
    member = GroupMemberFact(user, "LEADER")
    fact = GroupSnapshot("group", "class", 1, (member,))
    change = (
        {"group_id": ""}
        if invalid == "empty-group"
        else {"class_id": ""}
        if invalid == "empty-class"
        else {"source_version": True}
        if invalid == "bool-version"
        else {"source_version": -1}
        if invalid == "negative-version"
        else {"members": (member, member)}
        if invalid == "duplicate-member"
        else {"members": (replace(member, role="OWNER"),)}
        if invalid == "invalid-role"
        else {"members": (replace(member, status="PENDING"),)}
        if invalid == "invalid-status"
        else {"members": (replace(member, user_id="not-uuid"),)}
        if invalid == "invalid-user"
        else {"members": (replace(member, role="MEMBER"),)}
        if invalid == "no-leader"
        else {"members": (member, GroupMemberFact(uuid4(), "LEADER"))}
    )
    with pytest.raises(WorkError) as error:
        replace(fact, **change).validate()
    assert error.value.code == "CLASSROOM_UNAVAILABLE"
