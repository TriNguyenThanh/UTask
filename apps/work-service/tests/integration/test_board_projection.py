import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.tasks.models import Task

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_board_and_column_select_only_card_cursor_and_grouping_fields(
    created_project, board_tasks, actors, client_for
):
    Task.objects.filter(project_id=created_project["id"]).update(
        description_html="<p>" + "long content " * 1000 + "</p>",
        description_stripped="long content " * 1000,
        acceptance_criteria="acceptance " * 1000,
    )
    client = client_for(actors["member"])
    route = f"/projects/{created_project['id']}/kanban/"
    with CaptureQueriesContext(connection) as queries:
        reply = client.get(route, {"limit_per_column": 1})
        data = reply.json()["data"]
        column = next(row for row in data["columns"] if row["has_more"])
        page = client.get(
            route + f"states/{column['state_id']}/tasks/",
            {"cursor": column["next_cursor"], "page_size": 1},
        )
    assert reply.status_code == page.status_code == 200
    assert data["total_columns"] == 5 and data["total_tasks"] == 8
    assert page.json()["data"]["column_total_tasks"] == column["column_total_tasks"] == 4
    assert page.json()["data"]["tasks"][0]["id"] != column["tasks"][0]["id"]
    for card in [*column["tasks"], *page.json()["data"]["tasks"]]:
        assert set(card) == {"id", "code", "title", "sort_order", "version"}
    selects = [q["sql"] for q in queries if 'FROM "tasks"' in q["sql"]]
    assert selects
    assert all(
        not any(
            field in sql
            for field in ["description_html", "description_stripped", "acceptance_criteria"]
        )
        for sql in selects
    )
    assert len(queries) <= 20
