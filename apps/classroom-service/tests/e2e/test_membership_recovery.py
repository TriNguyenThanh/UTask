"""Real Kafka outage retains outbox; Redis/Celery recovers current membership."""

import pytest

from .http_client import wait_until
from .kafka_events import group_event
from .membership import members, publish, transfer

pytestmark = pytest.mark.e2e


def test_broker_outage_retains_outbox_and_celery_recovers_current_membership(
    api,
    environment,
    accounts,
    linked_projects,
):
    data = linked_projects
    # A shared session can contain outbox rows from earlier scenarios. Flush them while
    # Kafka is available so the bounded outage attempt targets this membership event.
    publish(environment)
    environment.command(
        "classroom",
        "shell",
        "-c",
        (
            "from apps.messaging.models import OutboxEvent; "
            "assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()"
        ),
    )
    environment.broker("stop")
    try:
        changed = transfer(api, accounts, data)
        stable = group_event(environment, data)
        publish(environment, time_budget=1)
        environment.command(
            "classroom",
            "shell",
            "-c",
            (
                "from apps.messaging.models import OutboxEvent; "
                f"e=OutboxEvent.objects.get(pk={stable['event_id']!r}); "
                "assert e.published_at is None and e.retry_count >= 1"
            ),
        )
        environment.command(
            "work",
            "shell",
            "-c",
            (
                "from apps.projects.tasks import recover_project_membership; "
                f"recover_project_membership.delay({data.projects[0]['id']!r})"
            ),
        )
        wait_until(
            lambda: (
                api(
                    "GET",
                    f"/api/work/projects/{data.projects[0]['id']}/",
                    token=accounts.tokens["teacher"],
                )["data"]["group_source_version"]
                == changed["source_version"]
            ),
            "real Celery/Redis recovery without Kafka or actor Bearer",
        )
        assert (
            next(
                row
                for row in members(api, accounts, data.projects[0])
                if row["user_id"] == accounts.users["member"]
            )["role"]
            == "LEADER"
        )
    finally:
        environment.broker("start")
        environment.compose("up", "-d", "--wait", "--wait-timeout", "120", "kafka")
    # Retry uses the same durable event, not a second domain event.
    publish(environment)
    environment.command(
        "classroom",
        "shell",
        "-c",
        (
            "from apps.messaging.models import OutboxEvent; "
            f"assert OutboxEvent.objects.get(pk={stable['event_id']!r}).published_at is not None"
        ),
    )
    assert group_event(environment, data)["event_id"] == stable["event_id"]
