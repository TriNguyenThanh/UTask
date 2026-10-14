from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.messaging.models import OutboxEvent
from apps.sprints.models import Sprint

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
]


def test_two_start_commands_cannot_create_two_active_sprints(
    created_project, actors, client_for, token
):
    from tests.fixtures.sprints import draft

    leader = client_for(actors["leader"])
    sprints = [draft(leader, created_project["id"], name) for name in ("A", "B")]
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def start(sprint):
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            response = client.post(
                f"/api/v1/projects/{created_project['id']}/sprints/{sprint['id']}/start/",
                {"expected_version": 1},
                format="json",
                HTTP_IDEMPOTENCY_KEY=sprint["id"],
            )
            return response.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, sprints)) == [200, 409]
    assert Sprint.objects.filter(project_id=created_project["id"], status="ACTIVE").count() == 1
    assert Sprint.objects.filter(project_id=created_project["id"], status="DRAFT").count() == 1
    assert OutboxEvent.objects.filter(event_type="sprint.started").count() == 1
