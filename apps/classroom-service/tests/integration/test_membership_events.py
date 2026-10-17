import jsonschema
import pytest

from apps.groups.services.groups import create_group
from apps.messaging.management.commands.export_event_contract import group_membership_schema
from apps.messaging.models import OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_membership_event_uses_generated_contract_and_stable_order(
    section, actors, command_request
):
    create_group(
        command_request(actors["leader"], "/groups/"), {"class_id": section.pk, "name": "Nhóm A"}
    )
    event = OutboxEvent.objects.get()
    jsonschema.Draft202012Validator(
        group_membership_schema(), format_checker=jsonschema.FormatChecker()
    ).validate(event.data)
    assert event.data["data"]["source_version"] == event.data["entity_version"]
    assert event.data["class_id"] == event.data["data"]["class_id"]
