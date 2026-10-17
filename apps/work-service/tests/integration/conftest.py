from dataclasses import replace
from uuid import UUID, uuid4

import pytest


@pytest.fixture
def classroom_projects(project_payload, actors, client_for, group, classroom):
    snapshot = replace(group, group_id=str(uuid4()), class_id=str(uuid4()))
    classroom.groups[snapshot.group_id] = snapshot
    project_payload = project_payload | {"classroom_group_id": snapshot.group_id}
    first = client_for(actors["leader"]).post(
        "/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="classroom-first-project"
    )
    assert first.status_code == 201
    second = client_for(actors["leader"]).post(
        "/projects/",
        project_payload | {"identifier": "CP2"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="classroom-second-project",
    )
    assert second.status_code == 201
    ids = [UUID(first.json()["data"]["id"]), UUID(second.json()["data"]["id"])]
    return ids, snapshot
