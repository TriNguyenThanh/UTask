from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_distinct_projects_in_same_group_both_commit(
    identity, token, actors, project_payload
):
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def create(index):
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            response = client.post(
                "/projects/",
                project_payload | {"identifier": f"GROUP{index}"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=f"same-group-distinct-{index}",
            )
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (1, 2)))
    assert [status for status, _ in results] == [201, 201]
    assert results[0][1]["data"]["id"] != results[1][1]["data"]["id"]
    assert (
        Project.objects.filter(
            classroom_group_id=project_payload["classroom_group_id"], archived_at__isnull=True
        ).count()
        == 2
    )
    assert IdempotencyRecord.objects.count() == 2
    assert OutboxEvent.objects.filter(event_type="project.created").count() == 2
