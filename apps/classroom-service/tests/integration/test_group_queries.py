from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_group_member_profiles_are_batched_queries_are_bounded_and_gets_have_no_effects(
    group, actors, client_for, identity
):
    client = client_for(actors["teacher"])
    before = (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
    )
    path = f"/groups/{group.pk}/members/"
    with CaptureQueriesContext(connection) as first:
        assert client.get(path).status_code == 200
    first_batches = len([call for call in identity["calls"] if call[0] == "users"])
    assert first_batches == 1
    for _ in range(15):
        enrollment = Enrollment.objects.create(class_section=group.class_section, user_id=uuid4())
        GroupMember.objects.create(
            class_section=group.class_section, group=group, enrollment=enrollment
        )
    with CaptureQueriesContext(connection) as second:
        response = client.get(path)
    assert response.status_code == 200 and len(response.json()["data"]) == 17
    assert len(second) <= len(first) + 1
    batches = [call for call in identity["calls"] if call[0] == "users"]
    assert len(batches) == 2 and len(batches[-1][1]) == 17
    for route in [
        "/courses/",
        "/classes/",
        f"/classes/{group.class_section_id}/teachers/",
        f"/classes/{group.class_section_id}/groups/",
        f"/groups/{group.pk}/",
        f"/groups/{group.pk}/projects/",
        f"/classes/{group.class_section_id}/activities/",
    ]:
        assert client.get(route).status_code == 200
    assert (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
    ) == before
