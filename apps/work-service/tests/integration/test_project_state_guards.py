from datetime import date
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.projects.models import Project, State
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "change",
    [{"start_date": "2027-01-21"}, {"end_date": "2027-01-09"}],
    ids=["start-after-end", "end-before-start"],
)
def test_partial_project_dates_reject_against_persisted_other_boundary(
    created_project, actors, client_for, change
):
    project = Project.objects.get(pk=created_project["id"])
    project.start_date, project.end_date = date(2027, 1, 10), date(2027, 1, 20)
    project.save(update_fields=["start_date", "end_date"])
    before = effect_state(project.pk)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project.pk}/",
        {"expected_version": project.version, **change},
        format="json",
    )
    assert reply.status_code == 400, reply.content
    assert effect_state(project.pk) == before


@pytest.mark.parametrize(
    "operation",
    [
        "create-slug",
        "patch-slug",
        "unset-default",
        "change-populated-group",
        "delete-populated",
        "delete-unknown",
    ],
)
def test_state_invalid_mutations_preserve_states_tasks_and_effects(task_api, operation):
    leader, task_route, create = task_api
    task = create()
    project_id = task["project_id"]
    root = f"/api/v1/projects/{project_id}/states/"
    state = State.objects.get(pk=task["state_id"])
    path = root + str(state.pk) + "/"
    if operation in ["change-populated-group", "delete-populated"]:
        state = State.objects.create(
            project_id=project_id,
            name="Populated",
            slug="populated",
            color="#123456",
            group="BACKLOG",
            sequence=99999,
        )
        create(state_id=str(state.pk))
        path = root + str(state.pk) + "/"
    before = effect_state(project_id)
    states = list(State.objects.order_by("id").values())
    if operation == "create-slug":
        reply = leader.post(
            root,
            {"name": "💡", "color": "#123456", "group": "BACKLOG", "sequence": 90000},
            format="json",
        )
    elif operation == "patch-slug":
        reply = leader.patch(path, {"name": "💡"}, format="json")
    elif operation == "unset-default":
        reply = leader.patch(path, {"is_default": False}, format="json")
    elif operation == "change-populated-group":
        reply = leader.patch(path, {"group": "STARTED"}, format="json")
    elif operation == "delete-populated":
        reply = leader.delete(path)
    else:
        reply = leader.delete(root + str(uuid4()) + "/")
    assert reply.status_code == (404 if operation == "delete-unknown" else 400), reply.content
    if operation in ["create-slug", "patch-slug"]:
        assert reply.json()["message"] == (
            "Tên cột trạng thái phải có ít nhất một chữ cái hoặc chữ số."
        )
    assert list(State.objects.order_by("id").values()) == states
    assert effect_state(project_id) == before


def test_capacity_inactive_target_rejects_without_any_effect(created_project, actors, client_for):
    project = Project.objects.get(pk=created_project["id"])
    project.members.filter(user_id=actors["member"]).update(status="LEFT", left_at=timezone.now())
    before = effect_state(project.pk)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project.pk}/members/{actors['member']}/capacity/",
        {"weekly_capacity": 8},
        format="json",
    )
    assert reply.status_code == 422 and reply.json()["error"]["code"] == "MEMBER_NOT_ACTIVE"
    assert effect_state(project.pk) == before


@pytest.mark.parametrize("kind", ["labels", "epics"])
def test_archived_project_metadata_write_does_not_allocate_or_emit(
    created_project, actors, client_for, kind
):
    Project.objects.filter(pk=created_project["id"]).update(archived_at=timezone.now())
    before = effect_state(created_project["id"])
    reply = client_for(actors["leader"]).post(
        f"/api/v1/projects/{created_project['id']}/{kind}/",
        {"name": "Denied", **({"color": "#123456"} if kind == "labels" else {})},
        format="json",
    )
    assert reply.status_code == 400, reply.content
    assert effect_state(created_project["id"]) == before
