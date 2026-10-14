from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from django.db import close_old_connections

from apps.messaging.models import OutboxEvent
from apps.tasks.models import Task, TaskRelation

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_assignment_subtask_whitelist_and_subtree_restore(task_api, actors, client_for):
    leader, _, create = task_api
    parent = create(due_date="2027-01-01")
    member = client_for(actors["member"])
    route = f"/api/v1/tasks/{parent['id']}/subtasks/"
    denied = member.post(
        route, {"title": "Con", "story_points": 3}, format="json", HTTP_IDEMPOTENCY_KEY="no"
    )
    assert denied.status_code == 403
    child_reply = member.post(route, {"title": "Con"}, format="json", HTTP_IDEMPOTENCY_KEY="child")
    assert child_reply.status_code == 201, child_reply.content
    child = child_reply.json()["data"]
    assert child["type"] == "SUBTASK"
    assert child["due_date"] == "2027-01-01"
    assert child["story_points"] is None
    assert child["assignee_ids"] == [str(actors["member"])]
    assert Task.objects.get(pk=parent["id"]).version == 1
    assert (
        member.post(route, {"title": "Con"}, format="json", HTTP_IDEMPOTENCY_KEY="child").json()[
            "data"
        ]
        == child
    )
    child_url = f"/api/v1/tasks/{child['id']}/"
    assert member.get(child_url).json()["data"] == child
    parent_read = member.get(f"/api/v1/tasks/{parent['id']}/").json()["data"]
    assert parent_read["subtasks_count"] == 1 and parent_read["version"] == 1
    assert leader.delete(child_url, {"expected_version": 1}, format="json").status_code == 200
    assert (
        leader.delete(
            f"/api/v1/tasks/{parent['id']}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert (
        leader.post(
            f"/api/v1/tasks/{parent['id']}/restore/", {"expected_version": 2}, format="json"
        ).status_code
        == 200
    )
    assert Task.objects.get(pk=child["id"]).deleted_at is not None


def test_relations_inverse_canonical_cycle_and_permission(task_api, actors, client_for):
    leader, _, create = task_api
    a, b, c = create(), create(), create(assignee_ids=[])

    def edge(source, target, kind="BLOCKS", client=leader):
        return client.post(
            f"/api/v1/tasks/{source['id']}/relations/",
            {"related_task_id": target["id"], "relation_type": kind},
            format="json",
        )

    assert edge(a, b).status_code == 201
    assert edge(b, a, "BLOCKED_BY").status_code == 409
    assert edge(b, c).status_code == 201
    event_count = OutboxEvent.objects.count()
    detail = leader.get(f"/api/v1/tasks/{b['id']}/", {"expand": "relations"})
    assert detail.status_code == 200, detail.content
    persisted = detail.json()["data"]
    assert persisted["version"] == Task.objects.get(pk=b["id"]).version == 2
    assert {(row["related_task_id"], row["relation_type"]) for row in persisted["relations"]} == {
        (a["id"], "BLOCKED_BY"),
        (c["id"], "BLOCKS"),
    }
    assert {UUID(row["id"]) for row in persisted["relations"]} == set(
        TaskRelation.objects.values_list("id", flat=True)
    )
    assert OutboxEvent.objects.count() == event_count
    cycle = edge(c, a)
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "DAG_CYCLE_DETECTED"
    assert TaskRelation.objects.count() == 2
    assert edge(c, a, "RELATES_TO", client_for(actors["member"])).status_code == 403
    response = edge(a, c, "RELATES_TO", client_for(actors["member"]))
    assert response.status_code == 201
    row = response.json()["data"]
    assert UUID(row["task_id"]) < UUID(row["related_task_id"])
    assert edge(c, a, "RELATES_TO").status_code == 409
    assert leader.delete(f"/api/v1/tasks/{b['id']}/relations/{row['id']}/").status_code == 404
    assert leader.delete(f"/api/v1/tasks/{a['id']}/relations/{row['id']}/").status_code == 200
    assert TaskRelation.objects.get(pk=row["id"]).deleted_at is not None
    reread = leader.get(f"/api/v1/tasks/{a['id']}/", {"expand": "relations"}).json()["data"]
    assert row["id"] not in {item["id"] for item in reread["relations"]}
    assert OutboxEvent.objects.filter(event_type="task.relation.deleted").count() == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_disjoint_edges_cannot_jointly_create_cycle(task_api, actors, client_for):
    leader, _, create = task_api
    a, b, c, d = [create() for _ in range(4)]
    for source, target in [(b, c), (d, a)]:
        assert (
            leader.post(
                f"/api/v1/tasks/{source['id']}/relations/",
                {"related_task_id": target["id"], "relation_type": "BLOCKS"},
                format="json",
            ).status_code
            == 201
        )
    barrier = Barrier(2)

    def add(pair):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            barrier.wait(timeout=10)
            source, target = pair
            return client.post(
                f"/api/v1/tasks/{source['id']}/relations/",
                {"related_task_id": target["id"], "relation_type": "BLOCKS"},
                format="json",
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(add, [(a, b), (c, d)]))
    assert statuses == [201, 409]
    assert TaskRelation.objects.filter(deleted_at__isnull=True).count() == 3
    assert OutboxEvent.objects.filter(event_type="task.relation.created").count() == 3
