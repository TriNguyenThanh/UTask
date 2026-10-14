import pytest

from apps.projects.models import Project
from apps.sprints.models import Sprint
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "resource", ["task-links", "project-archive", "capacity", "state", "label", "project", "sprint"]
)
def test_same_value_mutation_keeps_field_audit_and_follows_resource_version_contract(
    task_api, actors, resource
):
    leader, task_route, create = task_api
    task = create()
    project_id = task["project_id"]
    root = f"/api/v1/projects/{project_id}/"
    if resource == "task-links":
        path = f"/api/v1/tasks/{task['id']}/"
        body = {
            "expected_version": 1,
            "assignee_ids": task["assignee_ids"],
            "label_ids": task["label_ids"],
        }
    elif resource == "project-archive":
        path = root + "unarchive/"
        body = {"expected_version": Project.objects.get(pk=project_id).version}
    elif resource == "capacity":
        path = root + f"members/{actors['member']}/capacity/"
        body = {"weekly_capacity": 0}
    elif resource == "state":
        path = root + f"states/{task['state_id']}/"
        body = {"name": Project.objects.get(pk=project_id).states.get(pk=task["state_id"]).name}
    elif resource == "label":
        label = leader.post(
            root + "labels/", {"name": "Stable", "color": "#123456"}, format="json"
        ).json()["data"]
        path = root + f"labels/{label['id']}/"
        body = {"color": label["color"]}
    elif resource == "project":
        project = Project.objects.get(pk=project_id)
        path = root
        body = {"expected_version": project.version, "name": project.name}
    else:
        row = Sprint.objects.create(project_id=project_id, name="Stable")
        path = f"/api/v1/sprints/{row.pk}/"
        body = {"expected_version": 1, "name": row.name}
    before = effect_state(project_id)
    reply = (
        leader.post(path, body, format="json")
        if resource == "project-archive"
        else leader.patch(path, body, format="json")
    )
    assert reply.status_code == 200, reply.content
    after = effect_state(project_id)
    assert (
        after["activity"] == before["activity"]
        and after["idempotencyrecord"] == before["idempotencyrecord"]
    )
    if resource in ["task-links", "project-archive", "capacity"]:
        assert after == before
    else:
        assert len(after["outboxevent"]) == len(before["outboxevent"]) + 1
