import pytest

from apps.messaging.models import Activity
from apps.projects.models import Project, State

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_state_create_patch_default_tombstone_and_audit(created_project, client_for, actors):
    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/states/"
    response = client.post(
        path,
        {"name": "QA", "color": "#123456", "sequence": 45000, "group": "REVIEW"},
        format="json",
    )
    assert response.status_code == 201
    state_id = response.json()["data"]["id"]
    detail = path + state_id + "/"
    assert (
        client.patch(detail, {"name": "QA final", "is_default": True}, format="json").status_code
        == 200
    )
    assert State.objects.filter(project_id=created_project["id"], is_default=True).count() == 1
    assert client.delete(detail).json()["error"]["code"] == "INVALID_OPERATION"
    old = State.objects.get(project_id=created_project["id"], slug="backlog")
    assert (
        client.patch(path + str(old.pk) + "/", {"is_default": True}, format="json").status_code
        == 200
    )
    assert client.delete(detail).status_code == 200
    assert State.objects.get(pk=state_id).deleted_at is not None
    assert Activity.objects.filter(state_id=state_id).exists()
    assert len(client.get(path).json()["data"]) == 5
    assert Project.objects.get(pk=created_project["id"]).board_revision == 4


def test_state_unique_scope_member_permissions_and_invalid_target(
    created_project, client_for, actors
):
    path = f"/api/v1/projects/{created_project['id']}/states/"
    payload = {"name": "QA", "color": "#123456", "sequence": 45000, "group": "REVIEW"}
    assert client_for(actors["member"]).post(path, payload, format="json").status_code == 403
    client = client_for(actors["leader"])
    first = client.post(path, payload, format="json")
    assert first.status_code == 201
    duplicate = client.post(path, payload, format="json")
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "STATE_NAME_EXISTS"
    assert (
        client.post(path, payload | {"sequence": "NaN", "name": "bad"}, format="json").status_code
        == 400
    )
    detail = path + first.json()["data"]["id"] + "/"
    assert (
        client.delete(detail + "?target_state_id=" + first.json()["data"]["id"]).status_code == 400
    )
