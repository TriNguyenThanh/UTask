import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.projects.models import UserProjection
from apps.tasks.serializers.tasks import TaskSerializer
from tests.fixtures.collaboration import pending

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("count", [1, 10, 50])
def test_id_projection_omits_text_relations_and_counts_without_n_plus_one(task_api, count):
    leader, route, create = task_api
    tasks = [create(description_html="<p>Long content</p>") for _ in range(count)]
    with CaptureQueriesContext(connection) as captured:
        reply = leader.get(route, {"fields": "id", "page_size": 100})
    assert reply.status_code == 200, reply.content
    assert {row["id"] for row in reply.json()["data"]} == {row["id"] for row in tasks}
    assert all(set(row) == {"id"} for row in reply.json()["data"])
    assert reply.json()["meta"]["pagination"]["total_count"] == count
    sql = [query["sql"] for query in captured]
    print(f"projection count={count} queries={len(sql)}")
    selections = [query.split(" FROM ", 1)[0] for query in sql if query.startswith("SELECT")]
    for forbidden in [
        "description_html",
        "description_stripped",
        "acceptance_criteria",
        "blocked_reason",
        "subtasks_count",
        "comments_count",
        "attachments_count",
    ]:
        assert not any(forbidden in query for query in selections)
    assert not any(
        'FROM "task_assignments"' in query or 'FROM "task_labels"' in query for query in sql
    )
    assert len(sql) <= 4


@pytest.mark.parametrize("count", [1, 10, 50])
@pytest.mark.parametrize(
    "fields",
    ["id", "id,code,assignee_ids,label_ids,subtasks_count,comments_count,attachments_count"],
)
def test_projection_expansions_match_full_response_without_deferred_reads(
    task_api, actors, count, fields
):
    leader, route, create = task_api
    project = route.rsplit("tasks/", 1)[0]
    label = leader.post(
        project + "labels/", {"name": "Backend", "color": "#123456"}, format="json"
    ).json()["data"]
    epic = leader.post(project + "epics/", {"name": "Release"}, format="json").json()["data"]
    UserProjection.objects.create(
        user_id=actors["member"],
        display_name="Sinh viên",
        avatar_url=None,
        source_event_id="profile-projection",
        source_occurred_at=timezone.now(),
    )
    for _ in range(count):
        create(label_ids=[label["id"]], epic_id=epic["id"])
    expansions = "state,epic,labels,assignees"
    full = leader.get(route, {"page_size": 100, "expand": expansions}).json()
    with CaptureQueriesContext(connection) as captured:
        reply = leader.get(route, {"page_size": 100, "fields": fields, "expand": expansions})
    assert reply.status_code == 200, reply.content
    expected_fields = set(fields.split(",")) | set(expansions.split(","))
    assert reply.json()["data"] == [
        {key: value for key, value in row.items() if key in expected_fields} for row in full["data"]
    ]
    assert reply.json()["meta"] == full["meta"]
    sql = [query["sql"] for query in captured]
    assert len(sql) <= 7
    assert sum('FROM "task_assignments"' in query for query in sql) == 1
    assert sum('FROM "task_labels"' in query for query in sql) == 1
    assert not any(
        '"tasks"."description_html"' in query or '"tasks"."acceptance_criteria"' in query
        for query in sql
    )


def test_projection_validates_before_materialization_and_preserves_default_cursor_counts(task_api):
    leader, route, create = task_api
    first, second = create(title="First"), create(title="Second", priority="HIGH")
    default = leader.get(route).json()
    assert set(default["data"][0]) == set(TaskSerializer.Meta.fields)
    assert default["data"] == [second, first]
    for params in [{"fields": "unknown"}, {"expand": "subtasks"}, {"expand": "unknown"}]:
        with CaptureQueriesContext(connection) as captured:
            reply = leader.get(route, params)
        assert reply.status_code == 400
        assert not any('FROM "tasks"' in query["sql"] for query in captured)
    page = leader.get(route, {"fields": "id", "page_size": 1}).json()
    assert page["data"] == [{"id": second["id"]}]
    cursor = page["meta"]["pagination"]["next_cursor"]
    following = leader.get(route, {"cursor": cursor, "page_size": 1}).json()
    assert following["data"] == [first]
    assert following["meta"]["pagination"]["total_count"] == 2
    assert following["meta"]["pagination"]["has_next"] is False
    assert (
        leader.get(route, {"cursor": cursor, "priority": "HIGH", "fields": "id"}).status_code == 400
    )
    filtered = leader.get(route, {"fields": "id", "priority": "HIGH"}).json()
    assert filtered["data"] == [{"id": second["id"]}]
    assert filtered["meta"]["pagination"]["total_count"] == 1


def test_selected_counts_match_live_children_comments_and_confirmed_files(task_api, storage):
    leader, route, create = task_api
    parent = create()
    detail = f"/api/v1/tasks/{parent['id']}/"
    child = leader.post(
        detail + "subtasks/", {"title": "Child"}, format="json", HTTP_IDEMPOTENCY_KEY="child-count"
    )
    assert child.status_code == 201
    comment = leader.post(
        "/api/v1/comments/", {"task_id": parent["id"], "content_html": "Feedback"}, format="json"
    )
    assert comment.status_code == 201
    row = pending(leader, detail + "attachments/")
    confirmed = leader.post(
        detail + "attachments/",
        {"attachment_id": str(row.pk)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="file-count",
    )
    assert confirmed.status_code == 200
    params = {"fields": "id,subtasks_count,comments_count,attachments_count"}
    reply = leader.get(route, params)
    assert reply.status_code == 200
    projected = next(row for row in reply.json()["data"] if row["id"] == parent["id"])
    assert projected == {
        "id": parent["id"],
        "subtasks_count": 1,
        "comments_count": 1,
        "attachments_count": 1,
    }
    child_id = child.json()["data"]["id"]
    assert (
        leader.delete(
            f"/api/v1/tasks/{child_id}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert leader.delete(f"/api/v1/comments/{comment.json()['data']['id']}/").status_code == 200
    projected = leader.get(route, params).json()["data"][0]
    assert projected == {
        "id": parent["id"],
        "subtasks_count": 0,
        "comments_count": 0,
        "attachments_count": 1,
    }
