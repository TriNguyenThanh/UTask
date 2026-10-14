import pytest

from apps.projects.models import ProjectMember
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("capacity,status", [(2147483647, 200), (2147483648, 400), (-1, 400)])
def test_capacity_respects_existing_integer_storage_range(
    created_project, actors, client_for, capacity, status
):
    project_id = created_project["id"]
    before = effect_state(project_id)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project_id}/members/{actors['member']}/capacity/",
        {"weekly_capacity": capacity},
        format="json",
    )
    assert reply.status_code == status
    if status == 400:
        assert reply.json()["error"]["code"] == "VALIDATION_ERROR"
        assert reply.json()["error"]["details"][0]["field"] == "weekly_capacity"
        assert effect_state(project_id) == before
    else:
        assert ProjectMember.objects.get(user_id=actors["member"]).weekly_capacity == capacity
