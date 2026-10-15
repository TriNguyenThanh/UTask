from dataclasses import replace

import pytest

from apps.projects.models import Project

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_project_creation_rejects_well_formed_snapshot_for_different_group(
    classroom, group, project_payload, actors, client_for
):
    classroom.groups[group.group_id] = replace(group, group_id="other-group")
    before = Project.objects.count()
    reply = client_for(actors["leader"]).post(
        "/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="wrong-binding"
    )
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert Project.objects.count() == before == 0
    from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent

    assert (
        not Activity.objects.exists()
        and not IdempotencyRecord.objects.exists()
        and not OutboxEvent.objects.exists()
    )
