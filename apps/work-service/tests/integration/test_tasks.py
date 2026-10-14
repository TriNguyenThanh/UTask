from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, State
from apps.tasks.models import Task
from tests.fixtures.transactions import effect_state
from tests.fixtures.transactions import reject_outbox_event as reject_outbox_event

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_create_read_replay_and_scope(task_api, actors, client_for):
    leader, route, create = task_api
    task = create(
        key="create-1", description_html='<script>alert(1)</script><p onclick="evil()">An toàn</p>'
    )
    assert task["code"] == "UT-1"
    assert task["description_html"] == "<p>An toàn</p>"
    assert task["description_stripped"] == "An toàn"
    assert task["created_by_user_id"] == str(actors["leader"])
    assert task["assignee_ids"] == [str(actors["member"])]
    assert Activity.objects.filter(task_id=task["id"], verb="created").count() == 1
    assert OutboxEvent.objects.filter(event_type="task.created").count() == 1
    assert IdempotencyRecord.objects.filter(endpoint_path=route).count() == 1
    replay = create(
        key="create-1", description_html='<script>alert(1)</script><p onclick="evil()">An toàn</p>'
    )
    assert replay == task
    assert Task.objects.count() == 1
    assert Project.objects.get(pk=task["project_id"]).current_task_sequence == 1
    listing = leader.get(route + "?expand=assignees,state,labels&page_size=1").json()
    assert listing["data"][0]["id"] == task["id"]
    assert listing["data"][0]["state"]["id"] == task["state_id"]
    assert listing["data"][0]["assignees"][0]["user_id"] == str(actors["member"])
    detail_route = f"/api/v1/tasks/{task['id']}/"
    assert client_for(actors["member"]).get(detail_route).json()["data"]["title"] == task["title"]
    assert client_for(actors["teacher"]).get(detail_route).status_code == 200
    assert client_for(actors["outsider"]).get(detail_route).status_code == 404
    conflict = leader.post(route, {"title": "Khác"}, format="json", HTTP_IDEMPOTENCY_KEY="create-1")
    assert conflict.status_code == 422


def test_create_denials_rollback_and_revoked_replay(task_api, client_for, actors):
    leader, route, create = task_api
    assert leader.post(route, {"title": "Thiếu key"}, format="json").status_code == 400
    assert (
        client_for(actors["member"])
        .post(route, {"title": "Cấm"}, format="json", HTTP_IDEMPOTENCY_KEY="member")
        .status_code
        == 403
    )
    for payload in [
        {"state_id": str(uuid4())},
        {"assignee_ids": [str(actors["outsider"])]},
        {"label_ids": [str(uuid4())]},
    ]:
        response = leader.post(
            route,
            {"title": "Sai scope", **payload},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        assert response.status_code == 422
        assert not Task.objects.exists()
        assert Project.objects.get(pk=route.split("/")[4]).current_task_sequence == 0
        assert not IdempotencyRecord.objects.filter(endpoint_path=route).exists()
    create(key="permission")
    Project.objects.first().members.filter(user_id=actors["leader"]).update(role="MEMBER")
    response = leader.post(
        route,
        {"title": "Xây dựng API", "assignee_ids": [str(actors["member"])]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="permission",
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_create_audit_outbox_failure_rolls_back(task_api, reject_outbox_event):
    leader, route, _ = task_api
    project_id = route.split("/")[4]
    before = effect_state(project_id)
    with reject_outbox_event("task.created"):
        response = leader.post(
            route, {"title": "Rollback"}, format="json", HTTP_IDEMPOTENCY_KEY="rollback"
        )
    assert response.status_code == 500, response.content
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert not Task.objects.exists()
    assert not Activity.objects.filter(task__isnull=False).exists()
    assert Project.objects.get(pk=project_id).current_task_sequence == 0
    assert not IdempotencyRecord.objects.filter(endpoint_path=route).exists()
    assert effect_state(project_id) == before


def test_member_patch_version_and_lifecycle(task_api, client_for, actors):
    leader, route, create = task_api
    task = create()
    detail = f"/api/v1/tasks/{task['id']}/"
    member = client_for(actors["member"])
    response = member.patch(detail, {"expected_version": 1, "story_points": 8}, format="json")
    assert response.status_code == 403
    response = member.patch(
        detail, {"expected_version": 1, "description_html": "<p>Kết quả</p>"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["data"]["version"] == 2
    assert (
        leader.patch(detail, {"expected_version": 1, "priority": "HIGH"}, format="json").status_code
        == 409
    )
    assert (
        leader.post(detail + "archive/", {"expected_version": 2}, format="json").status_code == 200
    )
    assert leader.get(route).json()["data"] == []
    assert len(leader.get(route + "?status=archived").json()["data"]) == 1
    assert (
        member.patch(
            detail, {"expected_version": 3, "description_html": "Cấm"}, format="json"
        ).status_code
        == 400
    )
    assert (
        leader.post(detail + "unarchive/", {"expected_version": 3}, format="json").status_code
        == 200
    )
    assert leader.delete(detail, {"expected_version": 4}, format="json").status_code == 200
    assert leader.get(detail).status_code == 404
    assert leader.get(route).json()["meta"]["pagination"]["total_count"] == 0
    assert (
        leader.post(detail + "restore/", {"expected_version": 5}, format="json").status_code == 200
    )
    assert leader.get(detail).json()["data"]["deleted_at"] is None


def test_cursor_filters_expand_and_query_bound(task_api, django_assert_max_num_queries):
    leader, route, create = task_api
    first = create(title="API mới")
    create(title="Khác", priority="HIGH")
    page = leader.get(route + "?page_size=1&fields=id,code,title").json()
    assert set(page["data"][0]) == {"id", "code", "title"}
    cursor = page["meta"]["pagination"]["next_cursor"]
    second = leader.get(route, {"page_size": 1, "cursor": cursor}).json()
    assert second["data"][0]["id"] == first["id"]
    assert second["meta"]["pagination"]["has_next"] is False
    assert leader.get(route, {"cursor": cursor, "priority": "HIGH"}).status_code == 400
    assert leader.get(route, {"expand": "secrets"}).status_code == 400
    assert leader.get(route, {"fields": "ai_payload_hash"}).status_code == 400
    assert leader.get(route, {"search": first["code"]}).json()["data"][0]["id"] == first["id"]
    assert leader.get(route, {"priority": "INVALID"}).status_code == 400
    assert len(leader.get(route, {"sprint_id": "none"}).json()["data"]) == 2
    with django_assert_max_num_queries(10):
        response = leader.get(route + "?expand=assignees,state,labels")
        assert response.status_code == 200


def test_database_unique_sequence_scope_and_provenance(task_api):
    _, _, create = task_api
    task = Task.objects.get(pk=create()["id"])
    other = Project.objects.create(identifier="OTHER", name="Khác", classroom_group_id="other")
    state = State.objects.create(
        project=other,
        name="Backlog",
        slug="backlog",
        color="#123456",
        sequence=1,
        group="BACKLOG",
        is_default=True,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.filter(pk=task.pk).update(state=state)
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.filter(pk=task.pk).update(sequence_id=99)
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.create(
            project=task.project,
            state=task.state,
            sequence_id=task.sequence_id,
            title="Trùng",
            created_by_user_id=task.created_by_user_id,
        )


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False])
def test_parallel_create_counter_and_receipt(task_api, client_for, actors, same_key):
    _, route, _ = task_api
    barrier = Barrier(2)

    def send(index):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            barrier.wait(timeout=10)
            reply = client.post(
                route,
                {"title": "Race"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="same" if same_key else f"key-{index}",
            )
            assert reply.status_code == 201, reply.content
            return reply.json()["data"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [1, 2]))
    expected = 1 if same_key else 2
    assert Task.objects.count() == expected
    assert Project.objects.first().current_task_sequence == expected
    assert {row["sequence_id"] for row in results} == set(range(1, expected + 1))
    assert OutboxEvent.objects.filter(event_type="task.created").count() == expected


def test_task_integer_and_boolean_filter_reject_invalid_values(task_api):
    leader, route, _ = task_api
    response = leader.post(
        route,
        {"title": "Out of range", "story_points": 2147483648},
        format="json",
        HTTP_IDEMPOTENCY_KEY="overflow",
    )
    assert response.status_code == 400
    assert not Task.objects.exists()
    assert leader.get(route, {"is_blocked": "garbage"}).status_code == 400
    assert leader.get(route, {"is_blocked": "true"}).status_code == 200
    assert leader.get(route, {"is_blocked": "false"}).status_code == 200
