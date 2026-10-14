import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_subtask_expansion_limit_has_cursor_read_alternative(task_api, ai, actors, client_for):
    leader, route, create = task_api
    parent = create()
    ai(
        parent["project_id"],
        kind="SUBTASK",
        parent_id=parent["id"],
        revisions={f"child-{i}": "r1" for i in range(100)},
    )
    member = client_for(actors["member"])
    path = f"/api/v1/tasks/{parent['id']}/subtasks/"
    body = {
        "proposal_id": "proposal-1",
        "context_version": 42,
        "expected_parent_version": 1,
        "subtasks": [
            {"local_id": f"child-{i}", "ai_revision": "r1", "title": f"Child {i}"}
            for i in range(100)
        ],
    }
    reply = member.post(
        path + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="bounded-batch"
    )
    assert reply.status_code == 201, reply.content
    assert reply.json()["data"]["created_count"] == 100
    extra = member.post(
        path, {"title": "Child 101"}, format="json", HTTP_IDEMPOTENCY_KEY="child-101"
    )
    assert extra.status_code == 201, extra.content
    with CaptureQueriesContext(connection) as captured:
        detail = leader.get(f"/api/v1/tasks/{parent['id']}/", {"expand": "subtasks"})
    assert detail.status_code == 400, detail.content
    assert len(captured) <= 12
    first = leader.get(route, {"parent_id": parent["id"], "page_size": 100}).json()
    assert len(first["data"]) == 100 and first["meta"]["pagination"]["total_count"] == 101
    second = leader.get(
        route,
        {
            "parent_id": parent["id"],
            "page_size": 100,
            "cursor": first["meta"]["pagination"]["next_cursor"],
        },
    ).json()
    assert len(second["data"]) == 1 and not second["meta"]["pagination"]["has_next"]
    assert set(row["id"] for row in first["data"]).isdisjoint(row["id"] for row in second["data"])
    assert Task.objects.get(pk=parent["id"]).version == 1
