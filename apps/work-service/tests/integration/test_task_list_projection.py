import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.tasks.serializers.tasks import TaskSerializer

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
