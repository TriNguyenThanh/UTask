from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, transaction
from rest_framework.test import APIClient

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, ProjectMember, State
from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_create_read_replay_and_durable_effects(client_for, actors, project_payload):
    client = client_for(actors["leader"])
    first = client.post(
        "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="key"
    )
    assert first.status_code == 201
    body = first.json()
    assert set(body) == {"success", "message", "data", "meta", "error"}
    replay = client.post(
        "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="key"
    )
    assert replay.status_code == 201 and replay.json() == body
    data = body["data"]
    assert client.get(f"/api/v1/projects/{data['id']}/").json()["data"] == data
    assert (
        Project.objects.count()
        == IdempotencyRecord.objects.count()
        == Activity.objects.count()
        == OutboxEvent.objects.count()
        == 1
    )
    assert ProjectMember.objects.count() == 2
    assert State.objects.count() == 5 and State.objects.filter(is_default=True).count() == 1
    event = OutboxEvent.objects.get()
    assert event.project_sequence == event.data["project_sequence"] == 1
    assert event.data["event_id"] == str(event.pk)
    assert Project.objects.get().current_task_sequence == 0


def test_create_requires_group_leader_and_key(client_for, actors, project_payload):
    member = client_for(actors["member"])
    assert (
        member.post(
            "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="key"
        ).status_code
        == 403
    )
    leader = client_for(actors["leader"])
    assert (
        leader.post("/api/v1/projects/", project_payload, format="json").json()["error"]["code"]
        == "IDEMPOTENCY_KEY_REQUIRED"
    )
    assert not Project.objects.exists() and not IdempotencyRecord.objects.exists()


def test_input_spoof_dates_and_identifier_rejected(client_for, actors, project_payload):
    client = client_for(actors["leader"])
    for extra in (
        {"user_id": str(actors["leader"])},
        {"identifier": "bad-"},
        {"start_date": "2026-12-01", "end_date": "2026-10-01"},
    ):
        result = client.post(
            "/api/v1/projects/", project_payload | extra, format="json", HTTP_IDEMPOTENCY_KEY="key"
        )
        assert result.status_code == 400
        assert result.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not Project.objects.exists()


def test_reused_key_and_group_conflicts(created_project, client_for, actors, project_payload):
    client = client_for(actors["leader"])
    result = client.post(
        "/api/v1/projects/",
        project_payload | {"name": "changed"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="project-create",
    )
    assert result.status_code == 422
    result = client.post(
        "/api/v1/projects/",
        project_payload | {"identifier": "U2"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="other",
    )
    assert (
        result.status_code == 409
        and result.json()["error"]["code"] == "GROUP_PROJECT_ALREADY_EXISTS"
    )
    assert Project.objects.count() == 1


def test_replay_rechecks_current_membership(created_project, client_for, actors, project_payload):
    ProjectMember.objects.filter(user_id=actors["leader"]).update(
        status="LEFT", left_at=__import__("django.utils.timezone", fromlist=["now"]).now()
    )
    result = client_for(actors["leader"]).post(
        "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="project-create"
    )
    assert result.status_code == 404
    assert Project.objects.count() == 1


@pytest.mark.parametrize("boundary", ["record_activity", "emit_event", "save_receipt"])
def test_create_rolls_back_at_each_durable_boundary(
    monkeypatch, boundary, client_for, actors, project_payload
):
    def fail(*args, **kwargs):
        raise RuntimeError("boundary failed")

    monkeypatch.setattr("apps.projects.services.projects." + boundary, fail)
    response = client_for(actors["leader"]).post(
        "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="key"
    )
    assert response.status_code == 500
    assert all(
        model.objects.count() == 0
        for model in (Project, ProjectMember, State, Activity, OutboxEvent, IdempotencyRecord)
    )


def test_scope_teacher_readonly_capacity_and_archive(created_project, client_for, actors):
    path = f"/api/v1/projects/{created_project['id']}/"
    assert client_for(actors["outsider"]).get(path).status_code == 404
    teacher = client_for(actors["teacher"])
    assert teacher.get(path).status_code == 200
    assert teacher.patch(
        path, {"name": "teacher mutation", "expected_version": 1}, format="json"
    ).status_code in {403, 404}
    member = client_for(actors["member"])
    assert (
        member.patch(
            path, {"name": "member mutation", "expected_version": 1}, format="json"
        ).status_code
        == 403
    )
    leader = client_for(actors["leader"])
    capacity = path + f"members/{actors['member']}/capacity/"
    assert (
        leader.patch(capacity, {"weekly_capacity": 25}, format="json").json()["data"][
            "weekly_capacity"
        ]
        == 25
    )
    assert leader.patch(capacity, {"weekly_capacity": -1}, format="json").status_code == 400
    assert leader.post(path + "archive/", {"expected_version": 1}, format="json").status_code == 200
    assert (
        leader.patch(path, {"name": "frozen", "expected_version": 2}, format="json").status_code
        == 400
    )
    assert (
        leader.post(path + "unarchive/", {"expected_version": 2}, format="json").status_code == 200
    )
    assert (
        leader.patch(path, {"name": "stale", "expected_version": 2}, format="json").json()["error"][
            "code"
        ]
        == "VERSION_CONFLICT"
    )


def test_unarchive_uniqueness_and_identifier_retained(
    created_project, client_for, actors, project_payload
):
    client = client_for(actors["leader"])
    path = f"/api/v1/projects/{created_project['id']}/"
    assert client.post(path + "archive/", {"expected_version": 1}, format="json").status_code == 200
    other = client.post(
        "/api/v1/projects/",
        project_payload | {"identifier": "U2"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="other",
    )
    assert other.status_code == 201
    result = client.post(path + "unarchive/", {"expected_version": 2}, format="json")
    assert (
        result.status_code == 409
        and result.json()["error"]["code"] == "GROUP_PROJECT_ALREADY_EXISTS"
    )
    assert Project.objects.get(pk=created_project["id"]).archived_at is not None


def test_scoped_list_cursor_and_members(created_project, client_for, actors, classroom, settings):
    client = client_for(actors["leader"])
    for i in range(2, 5):
        group = GroupSnapshot(
            f"group-{i}", "class-1", 1, (GroupMemberFact(actors["leader"], "LEADER"),)
        )
        classroom.groups[group.group_id] = group
        assert (
            client.post(
                "/api/v1/projects/",
                {"identifier": f"U{i}", "name": str(i), "classroom_group_id": group.group_id},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(i),
            ).status_code
            == 201
        )
    first = client.get("/api/v1/projects/?page_size=2").json()
    assert len(first["data"]) == 2 and first["meta"]["pagination"]["total_count"] == 4
    cursor = first["meta"]["pagination"]["next_cursor"]
    last = client.get("/api/v1/projects/", {"page_size": 2, "cursor": cursor}).json()
    assert (
        not last["meta"]["pagination"]["has_next"]
        and last["meta"]["pagination"]["next_cursor"] is None
    )
    assert set(row["id"] for row in first["data"]).isdisjoint(row["id"] for row in last["data"])
    assert (
        client_for(actors["member"]).get("/api/v1/projects/", {"cursor": cursor}).status_code == 400
    )
    path = f"/api/v1/projects/{created_project['id']}/members/"
    assert len(client.get(path).json()["data"]) == 2

    settings.CLASSROOM_ADAPTER = "infrastructure.classroom.UnavailableClassroom"
    limited = client.get("/api/v1/projects/")
    assert limited.status_code == 200
    assert len(limited.json()["data"]) == 4
    assert limited.json()["meta"]["scope"] == {
        "partial": True,
        "source": "WORK_MEMBERSHIP",
        "teacher_scope": "UNAVAILABLE",
    }
    member_rows = client_for(actors["member"]).get("/api/v1/projects/").json()["data"]
    assert [row["id"] for row in member_rows] == [created_project["id"]]
    for role in ("outsider", "teacher"):
        response = client_for(actors[role]).get("/api/v1/projects/")
        assert response.status_code == 200 and response.json()["data"] == []
    assert client.get("/api/v1/projects/", {"classroom_group_id": "group-1"}).status_code == 503
    assert client.get("/api/v1/projects/", {"cursor": cursor}).status_code == 400


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_project_create_replays_one_mutation(identity, token, actors, project_payload):
    barrier = Barrier(2)
    credential = token(actors["leader"])

    def create():
        close_old_connections()
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + credential)
            barrier.wait(timeout=10)
            result = client.post(
                "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="race"
            )
            return result.status_code, result.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert results[0] == results[1] and results[0][0] == 201
    assert (
        Project.objects.count()
        == Activity.objects.count()
        == OutboxEvent.objects.count()
        == IdempotencyRecord.objects.count()
        == 1
    )


def test_database_rejects_invalid_state_and_member(created_project):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError), transaction.atomic():
        State.objects.filter(project_id=created_project["id"]).update(sequence=float("nan"))
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectMember.objects.create(
            project_id=created_project["id"],
            user_id=uuid4(),
            role="MEMBER",
            status="LEFT",
            joined_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
        )
