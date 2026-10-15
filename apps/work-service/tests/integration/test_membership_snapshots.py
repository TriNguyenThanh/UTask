from dataclasses import replace
from uuid import uuid4

import pytest

from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership
from common.errors import WorkError
from infrastructure.classroom import GroupMemberFact
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("mismatch", ["group", "class", "same-version-content"])
def test_membership_snapshot_scope_and_equal_version_conflicts_have_no_effect(
    created_project, group, actors, mismatch
):
    source = replace(
        group,
        **(
            {"group_id": "wrong-group"}
            if mismatch == "group"
            else {"class_id": "wrong-class"}
            if mismatch == "class"
            else {"members": (GroupMemberFact(actors["leader"], "LEADER"),)}
        ),
    )
    before = effect_state(created_project["id"])
    with pytest.raises(WorkError) as error:
        synchronize_membership(created_project["id"], source)
    assert error.value.code == (
        "SOURCE_VERSION_CONFLICT" if mismatch == "same-version-content" else "CLASSROOM_UNAVAILABLE"
    )
    assert effect_state(created_project["id"]) == before


def test_full_membership_snapshot_removes_omitted_slot_adds_member_and_preserves_capacity(
    created_project, group, actors, client_for
):
    project = Project.objects.get(pk=created_project["id"])
    old = project.members.get(user_id=actors["member"])
    old.weekly_capacity = 7
    old.save(update_fields=["weekly_capacity"])
    new_user = uuid4()
    source = replace(
        group,
        source_version=2,
        members=(GroupMemberFact(actors["leader"], "LEADER"), GroupMemberFact(new_user, "MEMBER")),
    )
    assert synchronize_membership(project.pk, source) is True
    old.refresh_from_db()
    project.refresh_from_db()
    assert old.status == "REMOVED" and old.left_at is not None and old.weekly_capacity == 7
    joined = project.members.get(user_id=new_user)
    assert joined.status == "ACTIVE" and joined.role == "MEMBER" and joined.joined_at is not None
    assert project.group_source_version == 2
    after = effect_state(project.pk)
    assert synchronize_membership(project.pk, source) is False
    assert effect_state(project.pk) == after
    assert client_for(actors["member"]).get(f"/projects/{project.pk}/").status_code == 404
    assert client_for(new_user).get(f"/projects/{project.pk}/").status_code == 200
