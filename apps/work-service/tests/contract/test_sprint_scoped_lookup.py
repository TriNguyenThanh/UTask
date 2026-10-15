from uuid import uuid4

import pytest
from django.db import connection

from apps.sprints.models import Sprint
from common.errors import WorkError
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize(
    "operation", ["detail", "progress", "burndown", "patch", "start", "scope", "close"]
)
@pytest.mark.parametrize("unavailable", [False, True])
def test_denied_and_missing_sprint_have_identical_response_before_write_validation(
    created_project, actors, client_for, classroom, monkeypatch, operation, unavailable
):
    sprint = Sprint.objects.create(project_id=created_project["id"], name="Private sprint")
    baseline_depth = len(connection.atomic_blocks)
    if unavailable:

        def fail(actor):
            assert len(connection.atomic_blocks) == baseline_depth
            raise WorkError(
                "CLASSROOM_UNAVAILABLE", "Không thể xác minh quyền xem chu kỳ làm việc.", 503
            )

        monkeypatch.setattr(classroom, "teacher_group_ids", staticmethod(fail))
    client = client_for(actors["outsider"])
    before = effect_state(created_project["id"])

    def request(sprint_id):
        route = f"/sprints/{sprint_id}/"
        if operation in {"progress", "burndown"}:
            route += operation + "/"
        if operation == "start":
            route = f"/projects/{created_project['id']}/sprints/{sprint_id}/start/"
        elif operation in {"scope", "close"}:
            route += "tasks/" if operation == "scope" else "close/"
        if operation in {"detail", "progress", "burndown"}:
            return client.get(route)
        return getattr(client, "patch" if operation == "patch" else "post")(
            route, {}, format="json", HTTP_IDEMPOTENCY_KEY="denied-sprint"
        )

    denied, missing = request(sprint.pk), request(uuid4())
    assert denied.status_code == missing.status_code == (503 if unavailable else 404)
    assert denied.json() == missing.json()
    assert effect_state(created_project["id"]) == before


@pytest.mark.parametrize("operation", ["detail", "progress", "burndown"])
def test_teacher_has_scoped_reads_and_members_read_without_classroom(
    created_project, actors, client_for, classroom, monkeypatch, operation
):
    sprint = Sprint.objects.create(project_id=created_project["id"], name="Visible sprint")
    route = f"/sprints/{sprint.pk}/" + ("" if operation == "detail" else operation + "/")
    teacher = client_for(actors["teacher"])
    assert teacher.get(route).status_code == 200
    denied = teacher.patch(f"/sprints/{sprint.pk}/", {}, format="json")
    assert (
        denied.status_code == 403
        and denied.json()["error"]["code"] == "TEACHER_MUTATION_RESTRICTED"
    )
    classroom.teachers[actors["teacher"]] = ["foreign-class-group"]
    assert teacher.get(route).status_code == 404
    depth = len(connection.atomic_blocks)

    def unavailable(actor):
        assert len(connection.atomic_blocks) == depth
        raise WorkError(
            "CLASSROOM_UNAVAILABLE", "Không thể xác minh quyền xem chu kỳ làm việc.", 503
        )

    monkeypatch.setattr(classroom, "teacher_group_ids", staticmethod(unavailable))
    assert teacher.get(route).status_code == 503
    assert client_for(actors["member"]).get(route).status_code == 200
