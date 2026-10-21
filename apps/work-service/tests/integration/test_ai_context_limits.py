from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.projects.models import ProjectMember
from apps.tasks.models import TaskAssignment
from tests.fixtures.ai_context import context_url

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("count", [0, 100, 101])
def test_array_limit_keeps_full_progress_counts(
    context_client, created_project, context_task_factory, context_schema, count
):
    context_task_factory(count=count, story_points=3, is_blocked=True, blocked_reason="Chờ đầu vào")
    client = context_client()
    project = client.get(context_url("project", created_project["id"], "project")).json()
    progress = client.get(context_url("project", created_project["id"], "progress")).json()
    assert len(project["data"]["tasks"]) == min(100, count)
    assert len(progress["data"]["blocked_tasks"]) == min(100, count)
    assert progress["data"]["total_tasks"] == count
    points = next(
        row for row in progress["data"]["metrics"] if row["name"] == "known_estimate_points"
    )
    assert points["value"] == count * 3
    assert project["status"] == ("partial" if count > 100 else "available")
    context_schema.validate(progress)


def test_unicode_document_limit_measures_actual_bytes_and_ignores_pretty_accept(
    context_client, created_project, context_task_factory, context_schema
):
    context_task_factory(count=100, title="ấ" * 300)
    url = context_url("project", created_project["id"], "project")
    response = context_client().get(url, HTTP_ACCEPT="application/json; indent=4")
    assert response.status_code == 200, response.content
    assert len(response.content) <= 65536
    document = response.json()
    assert document["status"] == "partial" and document["warning"]
    assert 0 < len(document["data"]["tasks"]) < 100
    context_schema.validate(document)
    assert (
        response.content == context_client().get(url).content
        or document["data"] == context_client().get(url).json()["data"]
    )


def test_team_totals_include_members_omitted_by_limit(
    context_client, created_project, context_task_factory
):
    members = [
        ProjectMember(
            project_id=created_project["id"],
            user_id=uuid4(),
            role="MEMBER",
            weekly_capacity=2,
            joined_at=timezone.now(),
        )
        for _ in range(101)
    ]
    ProjectMember.objects.bulk_create(members)
    task = context_task_factory(story_points=101)[0]
    TaskAssignment.objects.bulk_create(
        [TaskAssignment(task=task, user_id=member.user_id) for member in members]
    )
    document = context_client().get(context_url("project", created_project["id"], "team")).json()
    assert document["status"] == "partial"
    assert len(document["data"]["members"]) == 100
    assert document["data"]["capacity"] == 202 and document["data"]["workload"] == 101
    assert sum(row["workload"] for row in document["data"]["members"]) < 101


@pytest.mark.parametrize("domain", ["project", "team", "progress"])
def test_http_query_count_does_not_grow_per_task(
    context_client, created_project, context_task_factory, actors, domain
):
    first = context_task_factory(story_points=3)[0]
    TaskAssignment.objects.create(task=first, user_id=actors["member"])
    client = context_client()
    url = context_url("project", created_project["id"], domain)
    with CaptureQueriesContext(connection) as small:
        assert client.get(url).status_code == 200
    rows = context_task_factory(count=50, story_points=3)
    TaskAssignment.objects.bulk_create(
        [TaskAssignment(task=task, user_id=actors["member"]) for task in rows]
    )
    with CaptureQueriesContext(connection) as large:
        assert client.get(url).status_code == 200
    assert len(large) == len(small), [query["sql"] for query in large]
    assert len(large) < 20
