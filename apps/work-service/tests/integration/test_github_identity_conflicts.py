import pytest

from apps.projects.models import ProjectMember
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_leader_cannot_declare_another_members_username(created_project, actors, client_for):
    project_id = created_project["id"]
    before = effect_state(project_id)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project_id}/members/{actors['member']}/github/",
        {"github_username": "other-account"},
        format="json",
    )
    assert reply.status_code == 403 and reply.json()["error"]["code"] == "PERMISSION_DENIED"
    assert ProjectMember.objects.get(user_id=actors["member"]).github_username is None
    assert effect_state(project_id) == before


@pytest.mark.parametrize("username", ["same-user", "SAME-USER"])
def test_duplicate_username_returns_conflict_and_rolls_back_all_effects(
    created_project, actors, client_for, username
):
    project_id = created_project["id"]
    assert (
        client_for(actors["leader"])
        .patch(
            f"/api/v1/projects/{project_id}/members/{actors['leader']}/github/",
            {"github_username": "same-user"},
            format="json",
        )
        .status_code
        == 200
    )
    before = effect_state(project_id)
    members = list(ProjectMember.objects.order_by("id").values())
    reply = client_for(actors["member"]).patch(
        f"/api/v1/projects/{project_id}/members/{actors['member']}/github/",
        {"github_username": username},
        format="json",
    )
    assert reply.status_code == 409
    assert reply.json()["error"]["code"] == "DUPLICATE_GITHUB_USERNAME_IN_PROJECT"
    assert list(ProjectMember.objects.order_by("id").values()) == members
    assert effect_state(project_id) == before
