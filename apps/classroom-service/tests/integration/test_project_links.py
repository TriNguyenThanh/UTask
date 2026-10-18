from copy import deepcopy
from uuid import uuid4

import pytest

from apps.groups.models import GroupProjectLink
from apps.messaging.consumer import PoisonEvent, consume_event
from apps.messaging.models import Activity
from tests.fixtures.kafka import work_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_project_events_link_many_projects_deduplicate_and_quarantine_conflicts(group):
    event = work_event(group)
    assert consume_event(event) is True
    assert consume_event(event) is False
    assert consume_event(work_event(group)) is True
    assert (
        GroupProjectLink.objects.count()
        == Activity.objects.filter(verb="project.linked").count()
        == 2
    )
    conflict = deepcopy(event)
    conflict["data"]["classroom_group_id"] = str(uuid4())
    with pytest.raises(PoisonEvent):
        consume_event(conflict)
    assert GroupProjectLink.objects.count() == 2


@pytest.mark.parametrize("change", ["producer", "event_version", "data", "closed", "archived"])
def test_project_event_rejects_untrusted_invalid_or_inactive_target(group, change):
    event = work_event(group)
    if change == "closed":
        section = group.class_section
        section.status = "CLOSED"
        section.save()
    elif change == "archived":
        group.status = "ARCHIVED"
        group.save()
    else:
        event[change] = "invalid"
    with pytest.raises(PoisonEvent):
        consume_event(event)
    assert not GroupProjectLink.objects.exists()
