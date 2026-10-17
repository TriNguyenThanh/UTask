import json
from pathlib import Path

import jsonschema
import pytest

from apps.messaging.management.commands.export_event_contract import project_created_schema
from apps.messaging.models import OutboxEvent

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def test_project_created_event_matches_exported_actual_producer_schema(created_project):
    path = Path(__file__).resolve().parents[4] / "contracts/events/work.project.created.v1.json"
    exported = json.loads(path.read_text(encoding="utf-8"))
    assert exported == project_created_schema()
    event = OutboxEvent.objects.get(event_type="project.created").data
    jsonschema.Draft202012Validator(exported, format_checker=jsonschema.FormatChecker()).validate(
        event
    )
    assert event["data"]["id"] == created_project["id"]
    assert event["data"]["classroom_group_id"] == created_project["classroom_group_id"]
    assert event["data"]["class_id"] == created_project["class_id"]
