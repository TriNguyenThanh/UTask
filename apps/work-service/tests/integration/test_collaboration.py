import json
from uuid import UUID

import pytest

from apps.messaging.models import Activity, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Epic, Label, Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_label_epic_permissions_filter_and_tombstones(task_api, client_for, actors):
    leader, task_route, create = task_api
    project_id = task_route.split("/")[4]
    member = client_for(actors["member"])
    labels = f"/api/v1/projects/{project_id}/labels/"
    label = member.post(labels, {"name": "Backend", "color": "#123456"}, format="json").json()[
        "data"
    ]
    assert member.get(labels).json()["data"] == [label]
    before_revision = Project.objects.get(pk=project_id).board_revision
    changed = member.patch(
        labels + label["id"] + "/",
        {"color": "#abcdef", "description": "Đã kiểm API"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    label = changed.json()["data"]
    persisted = Label.objects.get(pk=label["id"])
    assert persisted.color == label["color"] == "#abcdef"
    assert persisted.description == label["description"] == "Đã kiểm API"
    assert Project.objects.get(pk=project_id).board_revision == before_revision + 1
    changes = Activity.objects.filter(label_id=label["id"], verb="updated")
    assert changes.count() == 2
    assert json.loads(changes.get(field="color").old_value) == "#123456"
    assert json.loads(changes.get(field="color").new_value) == "#abcdef"
    event = OutboxEvent.objects.get(event_type="label.updated")
    assert event.aggregate_id == label["id"] and event.data["data"] == label
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(labels)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [label]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    assert client_for(actors["outsider"]).get(labels).status_code == 404
    assert (
        leader.post(labels, {"name": "Backend", "color": "#123456"}, format="json").status_code
        == 409
    )
    task = create()
    task_url = f"/api/v1/tasks/{task['id']}/"
    response = member.post(
        task_url + "labels/",
        {"expected_version": 1, "action": "ADD", "label_ids": [label["id"]]},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["data"]["label_ids"] == [label["id"]]
    assert (
        leader.get(task_route, {"label_id": label["id"]}).json()["meta"]["pagination"][
            "total_count"
        ]
        == 1
    )
    assert member.delete(labels + label["id"] + "/").status_code == 403
    assert leader.delete(labels + label["id"] + "/").status_code == 200
    assert Label.objects.get(pk=label["id"]).deleted_at is not None
    assert member.get(labels).json()["data"] == []
    assert member.get(labels).json()["meta"]["pagination"]["total_count"] == 0
    assert leader.get(task_route, {"label_id": label["id"]}).json()["data"] == []
    epics = f"/api/v1/projects/{project_id}/epics/"
    epic = leader.post(
        epics, {"name": "Auth", "lead_user_id": str(actors["member"])}, format="json"
    ).json()["data"]
    updated = member.patch(epics + epic["id"] + "/", {"status": "IN_PROGRESS"}, format="json")
    assert updated.status_code == 200, updated.content
    epic = updated.json()["data"]
    persisted = Epic.objects.get(pk=epic["id"])
    assert persisted.status == epic["status"] == "IN_PROGRESS"
    assert persisted.lead_user_id == actors["member"]
    assert OutboxEvent.objects.get(event_type="epic.updated").data["data"] == epic
    for actor in ["leader", "member", "teacher"]:
        listed = client_for(actors[actor]).get(epics)
        assert listed.status_code == 200, listed.content
        assert listed.json()["data"] == [epic]
        assert listed.json()["meta"]["pagination"]["total_count"] == 1
    assert client_for(actors["outsider"]).get(epics).status_code == 404
    assert (
        member.patch(
            epics + epic["id"] + "/", {"target_date": "2027-01-01"}, format="json"
        ).status_code
        == 403
    )
    unrelated = create(assignee_ids=[], epic_id=epic["id"])
    assert (
        member.patch(
            f"/api/v1/tasks/{unrelated['id']}/",
            {"expected_version": 1, "description_html": "Forbidden"},
            format="json",
        ).status_code
        == 403
    )
    assert leader.delete(epics + epic["id"] + "/").status_code == 200
    assert Epic.objects.get(pk=epic["id"]).deleted_at is not None
    assert member.get(epics).json()["data"] == []
    assert Task.objects.get(pk=unrelated["id"]).epic_id == UUID(epic["id"])
    assert (
        leader.patch(
            f"/api/v1/tasks/{unrelated['id']}/",
            {"expected_version": 1, "title": "History preserved"},
            format="json",
        ).status_code
        == 200
    )
