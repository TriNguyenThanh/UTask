from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections

from apps.integrations.models import TaskGitHubLink
from apps.integrations.services.links import ingest_reference
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


@pytest.mark.parametrize("same_actor", [True, False])
def test_concurrent_github_confirmation_persists_one_owner_and_one_effect(
    github, actors, client_for, same_actor
):
    gateway, _, _, task = github
    fact = gateway.verify_reference(
        project_id=task.project_id,
        repo_id="repo-1",
        generation=1,
        link_type="PULL_REQUEST",
        github_ref_id="24",
    )
    candidate, _ = ingest_reference(task.pk, fact)
    route = f"/tasks/{task.pk}/github-links/{candidate.pk}/confirm/"
    before_task = Task.objects.filter(pk=task.pk).values().get()
    before_project = Project.objects.filter(pk=task.project_id).values().get()
    barrier = Barrier(2)
    writers = [actors["leader"], actors["leader"] if same_actor else actors["member"]]

    def confirm(index):
        close_old_connections()
        try:
            client = client_for(writers[index])
            barrier.wait(timeout=10)
            response = client.post(
                route, {}, format="json", HTTP_IDEMPOTENCY_KEY=f"concurrent-confirm-{index}"
            )
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, [0, 1]))
    assert [status for status, _ in results] == [200, 200]
    candidate.refresh_from_db()
    assert candidate.confirmation_status == "CONFIRMED"
    assert candidate.confirmed_by_user_id in writers and candidate.confirmed_at is not None
    assert TaskGitHubLink.objects.filter(task=task, deleted_at__isnull=True).count() == 1
    assert OutboxEvent.objects.filter(event_type="task.github_link.confirmed").count() == 1
    assert Activity.objects.filter(task=task, field="github_links", verb="confirmed").count() == 1
    assert IdempotencyRecord.objects.filter(endpoint_path=route).count() == 2
    for _, body in results:
        assert body["data"]["confirmed_by_user_id"] == str(candidate.confirmed_by_user_id)
    assert Task.objects.filter(pk=task.pk).values().get() == before_task
    project = Project.objects.get(pk=task.project_id)
    assert project.event_sequence == before_project["event_sequence"] + 1
    for index, actor in enumerate(writers):
        retry = client_for(actor).post(
            route, {}, format="json", HTTP_IDEMPOTENCY_KEY=f"concurrent-confirm-{index}"
        )
        assert retry.json() == results[index][1]
    assert OutboxEvent.objects.filter(event_type="task.github_link.confirmed").count() == 1
