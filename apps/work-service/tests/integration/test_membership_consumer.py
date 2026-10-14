import pytest

from apps.projects.models import ProjectMember
from apps.projects.services.membership import synchronize_membership
from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_membership_transfer_leave_rejoin_preserves_slot_and_capacity(
    created_project, actors, client_for
):
    path = f"/api/v1/projects/{created_project['id']}/"
    member = ProjectMember.objects.get(user_id=actors["member"])
    member.weekly_capacity = 25
    member.save()
    snapshot = GroupSnapshot(
        "group-1",
        "class-1",
        2,
        (
            GroupMemberFact(actors["leader"], "MEMBER", "LEFT"),
            GroupMemberFact(actors["member"], "LEADER"),
        ),
    )
    assert synchronize_membership(created_project["id"], snapshot)
    assert client_for(actors["leader"]).get(path).status_code == 404
    assert (
        client_for(actors["member"])
        .patch(path, {"name": "new leader", "expected_version": 2}, format="json")
        .status_code
        == 200
    )
    rejoin = GroupSnapshot(
        "group-1",
        "class-1",
        3,
        (GroupMemberFact(actors["leader"], "MEMBER"), GroupMemberFact(actors["member"], "LEADER")),
    )
    assert synchronize_membership(created_project["id"], rejoin)
    member.refresh_from_db()
    assert member.weekly_capacity == 25
    assert ProjectMember.objects.count() == 2
    assert not synchronize_membership(created_project["id"], snapshot)
    assert not synchronize_membership(created_project["id"], rejoin)
    assert ProjectMember.objects.get(user_id=actors["leader"]).left_at is None
