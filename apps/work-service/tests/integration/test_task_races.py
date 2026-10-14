from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID

import pytest
from django.db import close_old_connections

from apps.tasks.models import Task
from apps.tasks.services.hierarchy import reparent_task
from common.errors import WorkError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_deep_parent_cycle_rejected_and_detail_expand(task_api, actors):
    leader, route, create = task_api
    nodes = [create() for _ in range(6)]
    actor = SimpleNamespace(id=actors["leader"])
    for previous, current in zip(nodes[:-1], nodes[1:], strict=True):
        reparent_task(actor, UUID(current["id"]), UUID(previous["id"]), 1)
    with pytest.raises(WorkError, match="vòng lặp"):
        reparent_task(actor, UUID(nodes[0]["id"]), UUID(nodes[-1]["id"]), 1)
    detail = leader.get(
        f"/api/v1/tasks/{nodes[0]['id']}/", {"expand": "subtasks,relations,attachments"}
    )
    assert detail.status_code == 200, detail.content
    data = detail.json()["data"]
    assert [row["id"] for row in data["subtasks"]] == [nodes[1]["id"]]
    assert data["attachments"] == [] and data["relations"] == []
    from django.apps import apps

    github = leader.get(f"/api/v1/tasks/{nodes[0]['id']}/", {"expand": "github_links"})
    if apps.is_installed("apps.integrations"):
        assert github.status_code == 200 and github.json()["data"]["github_links"] == []
    else:
        assert github.status_code == 503


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_reparent_cannot_create_cycle(task_api, actors):
    _, _, create = task_api
    a, b = create(), create()
    barrier = Barrier(2)
    actor = SimpleNamespace(id=actors["leader"])

    def parent(pair):
        close_old_connections()
        try:
            source, target = pair
            barrier.wait(timeout=10)
            try:
                reparent_task(actor, UUID(source["id"]), UUID(target["id"]), 1)
                return 200
            except WorkError as exc:
                return exc.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(parent, [(a, b), (b, a)])) == [200, 409]
    assert Task.objects.filter(parent__isnull=False).count() == 1
