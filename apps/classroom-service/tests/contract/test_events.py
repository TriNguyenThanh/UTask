import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from apps.messaging.management.commands.export_event_contract import group_membership_schema
from apps.messaging.models import OutboxEvent

pytestmark = pytest.mark.contract
CONTRACT = Path(__file__).resolve().parents[4] / (
    "contracts/events/classroom.group.membership.changed.v1.json"
)


def test_exported_membership_schema_matches_runtime_producer_contract():
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == group_membership_schema()


@pytest.mark.django_db
def test_membership_change_outbox_validates_against_published_schema(
    group, actors, client_for, post_command
):
    response = post_command(
        client_for(actors["leader"]),
        f"/groups/{group.pk}/transfer-leader/",
        {"version": 1, "user_id": str(actors["member"]), "reason": "Luân phiên phụ trách"},
    )
    assert response.status_code == 200
    event = OutboxEvent.objects.get().data
    validator = Draft202012Validator(
        json.loads(CONTRACT.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )

    validator.validate(event)
    assert event["entity_version"] == event["data"]["source_version"]
    assert event["class_id"] == event["data"]["class_id"]
    assert event["aggregate_id"] == str(group.pk)

    # Both variants start from the real producer event, not a hand-built envelope.
    wrong_version = {**event, "event_version": 999}
    wrong_member_role = deepcopy(event)
    wrong_member_role["data"]["members"][0]["role"] = "ADMIN"
    for invalid in (wrong_version, wrong_member_role):
        with pytest.raises(ValidationError):
            validator.validate(invalid)
