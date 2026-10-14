from datetime import date

import pytest

from apps.tasks.models import Epic
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def dated_epic(created_project, client_for, actors):
    leader = client_for(actors["leader"])
    root = f"/api/v1/projects/{created_project['id']}/epics/"
    reply = leader.post(
        root,
        {"name": "Schedule", "start_date": "2027-01-10", "target_date": "2027-01-20"},
        format="json",
    )
    assert reply.status_code == 201, reply.content
    return leader, root + reply.json()["data"]["id"] + "/", reply.json()["data"]


@pytest.mark.parametrize("change", [{"start_date": "2027-01-21"}, {"target_date": "2027-01-09"}])
def test_partial_epic_date_conflict_preserves_saved_other_date_and_effects(dated_epic, change):
    leader, route, data = dated_epic
    before = effect_state(data["project_id"])
    reply = leader.patch(route, change, format="json")
    assert reply.status_code == 400 and reply.json()["error"]["code"] == "VALIDATION_ERROR"
    row = Epic.objects.get(pk=data["id"])
    assert row.start_date == date(2027, 1, 10) and row.target_date == date(2027, 1, 20)
    assert effect_state(data["project_id"]) == before
    assert leader.get(route.rsplit("/", 2)[0] + "/").json()["data"] == [data]


@pytest.mark.parametrize(
    "change",
    [
        {"start_date": "2027-01-20"},
        {"target_date": "2027-01-10"},
        {"start_date": None},
        {"target_date": None},
    ],
)
def test_partial_epic_date_update_reads_back_boundary_or_null(dated_epic, change):
    leader, route, data = dated_epic
    before = effect_state(data["project_id"])
    reply = leader.patch(route, change, format="json")
    assert reply.status_code == 200, reply.content
    row = Epic.objects.get(pk=data["id"])
    field, value = next(iter(change.items()))
    assert getattr(row, field) == (date.fromisoformat(value) if value else None)
    other = "target_date" if field == "start_date" else "start_date"
    assert getattr(row, other).isoformat() == data[other]
    listed = leader.get(route.rsplit("/", 2)[0] + "/").json()["data"]
    assert listed == [reply.json()["data"]]
    after = effect_state(data["project_id"])
    assert after["project"]["board_revision"] == before["project"]["board_revision"] + 1
    assert len(after["outboxevent"]) == len(before["outboxevent"]) + 1
    assert len(after["activity"]) == len(before["activity"]) + 1
    assert after["idempotencyrecord"] == before["idempotencyrecord"]
