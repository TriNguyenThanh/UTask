from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.sprints.models import Sprint
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "elapsed_days,expected_count,truncated", [(0, 1, False), (731, 732, False), (732, 732, True)]
)
def test_burndown_window_boundary_dates_totals_and_read_only_effects(
    created_project, actors, client_for, monkeypatch, elapsed_days, expected_count, truncated
):
    zone = ZoneInfo("Asia/Ho_Chi_Minh")
    captured = datetime(2026, 10, 10, 12, tzinfo=zone)
    started = captured - timedelta(days=elapsed_days)
    sprint = Sprint.objects.create(
        project_id=created_project["id"],
        name="Window",
        status="ACTIVE",
        started_at=started,
        start_date=started.date(),
        end_date=captured.date(),
    )
    monkeypatch.setattr("apps.sprints.queries.scope.timezone.now", lambda: captured)
    before = effect_state(created_project["id"])
    reply = client_for(actors["leader"]).get(f"/sprints/{sprint.pk}/burndown/")
    assert reply.status_code == 200, reply.content
    data = reply.json()["data"]
    assert data["window_truncated"] is truncated
    assert data["formula_version"] == "work-burndown-v1"
    assert len(data["days"]) == expected_count
    assert (
        data["days"][0]["date"]
        == max(started.date(), captured.date() - timedelta(days=731)).isoformat()
    )
    assert data["days"][-1]["date"] == captured.date().isoformat()
    assert all(
        row["scope_work_item_count"]
        == row["remaining_work_item_count"]
        == row["remaining_estimate_points"]
        == row["unestimated_remaining_count"]
        == 0
        for row in data["days"]
    )
    assert effect_state(created_project["id"]) == before


def test_burndown_draft_without_start_has_empty_window_and_no_effect(
    created_project, actors, client_for
):
    sprint = Sprint.objects.create(project_id=created_project["id"], name="Draft")
    before = effect_state(created_project["id"])
    reply = client_for(actors["leader"]).get(f"/sprints/{sprint.pk}/burndown/")
    assert reply.status_code == 200, reply.content
    data = reply.json()["data"]
    assert data == {
        "sprint_id": str(sprint.pk),
        "captured_at": data["captured_at"],
        "snapshot_version": None,
        "formula_version": "work-burndown-v1",
        "days": [],
        "window_truncated": False,
    }
    assert datetime.fromisoformat(data["captured_at"].replace("Z", "+00:00")).tzinfo is not None
    assert effect_state(created_project["id"]) == before
