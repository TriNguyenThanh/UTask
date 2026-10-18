from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.messaging.consumer import PoisonEvent, validate_work_event
from tests.fixtures.kafka import work_event

pytestmark = pytest.mark.unit


@pytest.fixture
def project_event():
    return work_event(SimpleNamespace(pk=uuid4(), class_section_id=uuid4()))


def test_project_created_event_returns_validated_logical_references(project_event):
    project_id, class_id, group_id = validate_work_event(project_event)
    assert str(project_id) == project_event["project_id"]
    assert str(class_id) == project_event["data"]["class_id"]
    assert str(group_id) == project_event["data"]["classroom_group_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("producer", "identity-service"),
        ("event_version", True),
        ("event_version", 2),
        ("event_id", "not-a-uuid"),
        ("occurred_at", "2026-01-01T00:00:00"),
        ("project_sequence", 0),
        ("project_sequence", True),
        ("entity_version", -1),
        ("entity_version", False),
        ("data", []),
    ],
)
def test_invalid_event_envelope_is_quarantined_before_linking(project_event, field, value):
    project_event[field] = value
    with pytest.raises(PoisonEvent):
        validate_work_event(project_event)


def test_project_reference_mismatch_is_quarantined(project_event):
    project_event["data"]["id"] = str(uuid4())
    with pytest.raises(PoisonEvent):
        validate_work_event(project_event)


def test_unrelated_valid_work_event_does_not_create_project_reference(project_event):
    project_event["event_type"] = "task.created"
    assert validate_work_event(project_event) is None
