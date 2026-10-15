from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.projects.models import Project, State
from apps.tasks.models import Task

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_board_all_columns_counts_keyset_ties_and_query_budget(
    created_project, board_tasks, client_for, actors
):
    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/kanban/"
    with CaptureQueriesContext(connection) as queries:
        response = client.get(path, {"limit_per_column": 2})
    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["total_columns"] == 5 and data["total_tasks"] == 8
    assert len(queries) <= 10
    assert sum(c["column_total_tasks"] for c in data["columns"]) == 8
    for column in data["columns"]:
        assert len(column["tasks"]) <= 2
        if not column["has_more"]:
            assert column["next_cursor"] is None
            assert len(column["tasks"]) == column["column_total_tasks"]
            continue
        next_page = client.get(
            path + f"states/{column['state_id']}/tasks/",
            {"page_size": 2, "cursor": column["next_cursor"]},
        ).json()["data"]
        assert not next_page["has_more"]
        assert {t["id"] for t in column["tasks"]}.isdisjoint(t["id"] for t in next_page["tasks"])
        assert next_page["column_total_tasks"] == 4


def test_board_cursor_revision_scope_filter_and_tamper(
    created_project, board_tasks, client_for, actors
):
    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/kanban/"
    column = next(
        c
        for c in client.get(path, {"limit_per_column": 1}).json()["data"]["columns"]
        if c["has_more"]
    )
    route = path + f"states/{column['state_id']}/tasks/"
    cursor = column["next_cursor"]
    assert client.get(route, {"cursor": cursor, "priority": "HIGH"}).status_code == 400
    assert client_for(actors["member"]).get(route, {"cursor": cursor}).status_code == 400
    assert client.get(route, {"cursor": cursor + "tampered"}).status_code == 400
    Project.objects.filter(pk=created_project["id"]).update(board_revision=1)
    conflict = client.get(route, {"cursor": cursor})
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "BOARD_REVISION_CHANGED"
    )


def test_board_filters_do_not_fan_out_and_hide_deleted_archived_tasks(
    created_project, board_tasks, client_for, actors
):
    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/kanban/"
    assert (
        client.get(path, {"assignee_id": str(actors["leader"])}).json()["data"]["total_tasks"] == 1
    )
    Task.objects.filter(pk=board_tasks[2].pk).update(deleted_at=timezone.now())
    Task.objects.filter(pk=board_tasks[3].pk).update(archived_at=timezone.now())
    assert client.get(path).json()["data"]["total_tasks"] == 6
    assert client.get(path, {"assignee_id": str(uuid4())}).json()["data"]["total_tasks"] == 0
    assert client_for(actors["outsider"]).get(path).status_code == 404
    assert client_for(actors["teacher"]).get(path).status_code == 200
    assert client.get(path, {"priority": "BAD"}).status_code == 400


def test_board_cursor_cannot_be_reused_in_another_state_or_project(
    created_project, board_tasks, client_for, actors
):
    from apps.projects.models import ProjectMember

    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/kanban/"
    columns = client.get(path, {"limit_per_column": 1}).json()["data"]["columns"]
    source = next(c for c in columns if c["has_more"])
    other_state = next(c for c in columns if c["state_id"] != source["state_id"])
    response = client.get(
        path + f"states/{other_state['state_id']}/tasks/", {"cursor": source["next_cursor"]}
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    other = Project.objects.create(
        identifier="U2", name="Other scope", classroom_group_id="group-2"
    )
    ProjectMember.objects.create(
        project=other, user_id=actors["leader"], role="LEADER", joined_at=timezone.now()
    )
    state = State.objects.create(
        project=other,
        name="Backlog",
        slug="backlog",
        color="#123456",
        sequence=10000,
        group="BACKLOG",
        is_default=True,
    )
    response = client.get(
        f"/api/v1/projects/{other.pk}/kanban/states/{state.pk}/tasks/",
        {"cursor": source["next_cursor"]},
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"
