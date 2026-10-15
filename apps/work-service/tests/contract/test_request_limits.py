import json
from urllib.parse import urlencode

import pytest

from apps.projects.models import Project
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("content_type", ["application/json", "application/x-www-form-urlencoded"])
def test_oversized_request_is_rejected_without_saved_changes(
    created_project, client_for, actors, settings, content_type
):
    leader = client_for(actors["leader"])
    route = f"/projects/{created_project['id']}/"
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
    payload = {"expected_version": 1, "description": "x" * 1025}
    body = json.dumps(payload) if content_type == "application/json" else urlencode(payload)
    before = effect_state(created_project["id"])
    reply = leader.patch(route, data=body, content_type=content_type)
    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "VALIDATION_ERROR"
    assert reply.json()["data"] is None
    assert effect_state(created_project["id"]) == before

    saved = leader.patch(route, {"expected_version": 1, "description": "Valid"}, format="json")
    assert saved.status_code == 200
    project = Project.objects.get(pk=created_project["id"])
    assert project.description == "Valid" and project.version == 2
    assert leader.get(route).json()["data"]["description"] == "Valid"


def test_deeply_nested_json_returns_validation_error_without_mutation(
    created_project, client_for, actors
):
    before = effect_state(created_project["id"])
    body = '{"expected_version":1,"tech_stack":{"nested":' + "[" * 1500 + "0" + "]" * 1500 + "}}"
    reply = client_for(actors["leader"]).patch(
        f"/projects/{created_project['id']}/", body, content_type="application/json"
    )
    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "RecursionError" not in reply.content.decode()
    assert effect_state(created_project["id"]) == before
