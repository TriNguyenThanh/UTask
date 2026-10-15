from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.projects.metrics import allocate_points
from apps.projects.models import State
from apps.tasks.models import Label, Task, TaskAssignment, TaskLabel, TaskRelation

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_dashboard_scope_estimate_coverage_parent_child_and_fanout(
    created_project, actors, client_for, monkeypatch
):
    monkeypatch.setattr(
        "apps.projects.queries.dashboard.timezone.now",
        lambda: datetime(2026, 12, 1, 17, 30, tzinfo=UTC),
    )
    project_id = created_project["id"]
    states = {s.group: s for s in State.objects.filter(project_id=project_id)}
    cancel = State.objects.create(
        project_id=project_id,
        name="Cancelled",
        slug="cancelled",
        color="#123456",
        sequence=60000,
        group="CANCELLED",
    )

    def task(sequence, state, **fields):
        if state.group == "COMPLETED":
            fields["completed_at"] = datetime(2026, 12, 1, 17, 30, tzinfo=UTC)
        return Task.objects.create(
            project_id=project_id,
            sequence_id=sequence,
            state=state,
            title=str(sequence),
            created_by_user_id=actors["leader"],
            **fields,
        )

    parent = task(1, states["BACKLOG"], story_points=5)
    task(2, states["COMPLETED"], parent=parent, type="SUBTASK", story_points=99)
    task(3, states["COMPLETED"], story_points=0)
    task(4, cancel, story_points=7, due_date="2026-12-01")
    unknown = task(
        5, states["BACKLOG"], due_date="2026-12-01", is_blocked=True, blocked_reason="wait"
    )
    TaskAssignment.objects.create(task=parent, user_id=actors["leader"])
    TaskAssignment.objects.create(task=parent, user_id=actors["member"])
    for i in range(3):
        label = Label.objects.create(project_id=project_id, name=str(i), color="#123456")
        TaskLabel.objects.create(task=parent, label=label)
    TaskRelation.objects.create(task=parent, related_task=unknown, relation_type="BLOCKS")
    path = f"/api/v1/projects/{project_id}/dashboard/"
    with CaptureQueriesContext(connection) as queries:
        reply = client_for(actors["teacher"]).get(path)
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 13
    data = reply.json()["data"]
    assert data["business_date"] == "2026-12-02"
    totals = data["totals"]
    assert totals["task_count"] == 5 and totals["work_item_count"] == 4
    assert totals["known_estimate_points"] == 12 and totals["completed_estimate_points"] == 0
    assert totals["cancelled_estimate_points"] == 7
    assert totals["estimated_count"] == 3 and totals["unestimated_count"] == 1
    assert totals["completion_percent"] == 25
    assert (
        totals["overdue_task_count"]
        == totals["blocked_task_count"]
        == totals["dependency_blocked_task_count"]
        == 1
    )
    assert sum(
        Decimal(str(row["allocated_estimate_points"])) for row in data["assignee_distribution"]
    ) == Decimal(5)
    assert data["unassigned_estimate_points"] == 7
    assert client_for(actors["outsider"]).get(path).status_code == 404


def test_empty_dashboard_and_fractional_allocation(created_project, actors, client_for):
    data = (
        client_for(actors["leader"])
        .get(f"/api/v1/projects/{created_project['id']}/dashboard/")
        .json()["data"]
    )
    assert data["totals"]["completion_percent"] is None
    assert data["totals"]["known_estimate_points"] == 0
    users = [uuid4() for _ in range(3)]
    allocation = allocate_points(1, users)
    assert sum(allocation.values()) == 1
    assert set(allocation.values()) == {Decimal("0.33"), Decimal("0.34")}


def test_dashboard_excludes_archived_deleted_and_denies_teacher_outside_class(
    task_api, created_project, client_for, actors, classroom
):
    leader, _, create = task_api
    live = create(story_points=0)
    archived = create(story_points=13)
    deleted = create(story_points=21)
    unknown = create()
    assert (
        leader.post(
            f"/api/v1/tasks/{archived['id']}/archive/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert (
        leader.delete(
            f"/api/v1/tasks/{deleted['id']}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    route = f"/api/v1/projects/{created_project['id']}/dashboard/"
    response = client_for(actors["teacher"]).get(route)
    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["totals"]["work_item_count"] == data["totals"]["task_count"] == 2
    assert data["totals"]["known_estimate_points"] == 0
    assert data["totals"]["estimated_count"] == data["totals"]["unestimated_count"] == 1
    assert sum(row["task_count"] for row in data["state_distribution"]) == 2
    assert sum(row["assigned_work_item_count"] for row in data["assignee_distribution"]) == 2
    assert Task.objects.get(pk=live["id"]).story_points == 0
    assert Task.objects.get(pk=unknown["id"]).story_points is None
    classroom.teachers[actors["teacher"]] = ["different-class-group"]
    assert client_for(actors["teacher"]).get(route).status_code == 404
