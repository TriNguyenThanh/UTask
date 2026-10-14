from datetime import date

import pytest
from django.utils import timezone

from apps.projects.models import Project
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "change",
    [{"start_date": "2027-01-21"}, {"end_date": "2027-01-09"}],
    ids=["start-after-end", "end-before-start"],
)
def test_partial_project_dates_reject_against_persisted_other_boundary(
    created_project, actors, client_for, change
):
    project = Project.objects.get(pk=created_project["id"])
    project.start_date, project.end_date = date(2027, 1, 10), date(2027, 1, 20)
    project.save(update_fields=["start_date", "end_date"])
    before = effect_state(project.pk)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project.pk}/",
        {"expected_version": project.version, **change},
        format="json",
    )
    assert reply.status_code == 400, reply.content
    assert effect_state(project.pk) == before


def test_capacity_inactive_target_rejects_without_any_effect(created_project, actors, client_for):
    project = Project.objects.get(pk=created_project["id"])
    project.members.filter(user_id=actors["member"]).update(status="LEFT", left_at=timezone.now())
    before = effect_state(project.pk)
    reply = client_for(actors["leader"]).patch(
        f"/api/v1/projects/{project.pk}/members/{actors['member']}/capacity/",
        {"weekly_capacity": 8},
        format="json",
    )
    assert reply.status_code == 422 and reply.json()["error"]["code"] == "MEMBER_NOT_ACTIVE"
    assert effect_state(project.pk) == before
