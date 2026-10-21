from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, ProjectMember, State
from apps.projects.queries.ai_context import read_ai_context
from apps.projects.serializers.ai_context import ContextDocumentSerializer
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task, TaskAssignment, TaskRelation
from common.authentication import Actor
from tests.fixtures.ai_context import context_url
from tests.fixtures.sprints import draft

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "target_type,domain",
    [
        ("project", "project"),
        ("project", "team"),
        ("project", "progress"),
        ("task", "task"),
        ("task", "project"),
        ("task", "team"),
        ("task", "progress"),
        ("sprint", "project"),
        ("sprint", "team"),
        ("sprint", "progress"),
    ],
)
def test_serialization_uses_captured_data_without_database_reads(
    context_targets, context_schema, actors, target_type, domain
):
    facts = read_ai_context(
        Actor(actors["member"]), target_type, context_targets[target_type], domain
    )
    with CaptureQueriesContext(connection) as queries:
        document = ContextDocumentSerializer(facts).data
    assert len(queries) == 0
    context_schema.validate(document)


def test_empty_project_is_available_and_zero_denominator_is_null(
    context_client, created_project, context_schema
):
    client = context_client()
    for domain in ("project", "team", "progress"):
        response = client.get(context_url("project", created_project["id"], domain))
        assert response.status_code == 200
        document = response.json()
        assert document["status"] == "available"
        context_schema.validate(document)
        if domain == "progress":
            assert document["data"]["total_tasks"] == 0
            metric = next(
                item for item in document["data"]["metrics"] if item["name"] == "completion_percent"
            )
            assert metric["value"] is None


def test_team_uses_remaining_root_points_and_capacity_hours(
    context_client, created_project, context_task_factory, actors
):
    project_id = created_project["id"]
    roots = context_task_factory(count=4, story_points=5)
    completed = State.objects.get(project_id=project_id, group="COMPLETED")
    cancelled = State.objects.create(
        project_id=project_id,
        name="Hủy",
        slug="cancelled",
        group="CANCELLED",
        color="#000000",
        sequence=99,
    )
    Task.objects.filter(pk=roots[1].pk).update(state=completed, completed_at=timezone.now())
    Task.objects.filter(pk=roots[2].pk).update(state=cancelled)
    Task.objects.filter(pk=roots[3].pk).update(archived_at=timezone.now())
    child = context_task_factory(story_points=99, parent=roots[0], type="SUBTASK")[0]
    for task in [*roots, child]:
        TaskAssignment.objects.create(task=task, user_id=actors["member"])
    TaskAssignment.objects.create(task=roots[0], user_id=actors["leader"])
    ProjectMember.objects.filter(project_id=project_id, user_id=actors["member"]).update(
        weekly_capacity=20
    )
    ProjectMember.objects.filter(project_id=project_id, user_id=actors["leader"]).update(
        weekly_capacity=10
    )
    response = context_client().get(context_url("project", project_id, "team"))
    document = response.json()
    assert document["status"] == "available"
    assert document["data"]["capacity"] == 30 and document["data"]["workload"] == 5
    assert {row["workload"] for row in document["data"]["members"]} == {2.5}
    assert "giờ/tuần" in document["warning"] and "điểm ước lượng" in document["warning"]


def test_team_unknown_and_inactive_assignments_do_not_redistribute(
    context_client, created_project, context_task_factory, actors
):
    known, missing, unassigned = context_task_factory(count=3, story_points=5)
    Task.objects.filter(pk=missing.pk).update(story_points=None)
    departed = uuid4()
    ProjectMember.objects.create(
        project_id=created_project["id"], user_id=departed, role="MEMBER", joined_at=timezone.now()
    )
    TaskAssignment.objects.bulk_create(
        [
            TaskAssignment(task=known, user_id=actors["member"]),
            TaskAssignment(task=known, user_id=departed),
            TaskAssignment(task=missing, user_id=actors["member"]),
        ]
    )
    ProjectMember.objects.filter(project_id=created_project["id"], user_id=departed).update(
        status="LEFT", left_at=timezone.now()
    )
    document = context_client().get(context_url("project", created_project["id"], "team")).json()
    assert document["status"] == "partial"
    assert document["data"]["workload"] == 2.5
    assert departed not in [row["user_id"] for row in document["data"]["members"]]
    assert "chưa có điểm" in document["warning"] and "chưa được phân công" in document["warning"]


def test_task_dependencies_are_incoming_visible_blockers(
    context_client, context_task_factory, created_project
):
    blocker, task, outbound, hidden = context_task_factory(count=4)
    Task.objects.filter(pk=hidden.pk).update(deleted_at=timezone.now())
    TaskRelation.objects.bulk_create(
        [
            TaskRelation(task=blocker, related_task=task, relation_type="BLOCKS"),
            TaskRelation(task=task, related_task=outbound, relation_type="BLOCKS"),
            TaskRelation(task=hidden, related_task=task, relation_type="BLOCKS"),
        ]
    )
    other = Project.objects.create(identifier="OTHER", name="Other", classroom_group_id="elsewhere")
    state = State.objects.create(
        project=other, name="Other", slug="other", group="BACKLOG", color="#000000", sequence=1
    )
    Task.objects.create(
        project=other, state=state, sequence_id=1, title="Private", created_by_user_id=uuid4()
    )
    document = context_client().get(context_url("task", task.pk, "task")).json()
    assert document["data"]["dependencies"] == [str(blocker.pk)]
    project = context_client().get(context_url("task", task.pk, "project")).json()
    assert project["data"]["id"] == created_project["id"]
    assert "Private" not in str(project)


def test_sprint_progress_scopes_tasks_but_team_remains_project(
    context_client, context_targets, context_task_factory
):
    scoped, outside = context_task_factory(count=2, story_points=3)
    SprintTask.objects.create(
        sprint_id=context_targets["sprint"], task=scoped, added_at=timezone.now()
    )
    client = context_client()
    sprint_progress = client.get(
        context_url("sprint", context_targets["sprint"], "progress")
    ).json()
    project_progress = client.get(
        context_url("project", context_targets["project"], "progress")
    ).json()
    assert sprint_progress["data"]["total_tasks"] == 1
    assert project_progress["data"]["total_tasks"] == 3
    assert ":" in sprint_progress["source_version"]
    assert (
        client.get(context_url("sprint", context_targets["sprint"], "team")).json()["data"]
        == client.get(context_url("project", context_targets["project"], "team")).json()["data"]
    )


def test_completed_sprint_returns_truthful_frozen_stale_data(
    context_client, task_api, created_project
):
    leader, _, create = task_api
    task = create(story_points=5)
    sprint = draft(leader, created_project["id"], "Closed")
    listing = f"/projects/{created_project['id']}/sprints/"
    detail = f"/sprints/{sprint['id']}/"
    assert (
        leader.post(
            detail + "tasks/",
            {"action": "ADD", "task_ids": [task["id"]], "expected_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY="context-add",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            listing + sprint["id"] + "/start/",
            {"expected_version": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="context-start",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            detail + "close/",
            {"expected_version": 3},
            format="json",
            HTTP_IDEMPOTENCY_KEY="context-close",
        ).status_code
        == 200
    )
    closed = Sprint.objects.get(pk=sprint["id"])
    before = context_client().get(context_url("sprint", closed.pk, "progress")).json()
    Task.objects.filter(pk=task["id"]).update(title="Changed later", story_points=99)
    Project.objects.filter(pk=created_project["id"]).update(event_sequence=99999)
    after = context_client().get(context_url("sprint", closed.pk, "progress")).json()
    assert before == after
    assert after["status"] == "stale" and after["warning"]
    assert after["as_of"] == closed.closure_snapshot["captured_at"]
    assert (
        after["source_version"]
        == f"{closed.version}:{closed.closure_snapshot['cut_project_sequence']}"
    )
    assert "Changed later" not in str(after)


def test_context_redacts_html_email_and_credentials(context_client, context_task_factory):
    task = context_task_factory()[0]
    Task.objects.filter(pk=task.pk).update(
        description_stripped="<b>Text</b> x@example.com token=private-value Bearer abc.def ghi",
        acceptance_criteria="github_pat_private123",
    )
    response = context_client().get(context_url("task", task.pk, "task"))
    raw = response.content.decode()
    assert response.json()["status"] == "partial"
    for private in ("<b>", "x@example.com", "private-value", "abc.def", "github_pat_private123"):
        assert private not in raw


def test_read_and_authorize_have_no_durable_side_effects(context_client, context_targets):
    client = context_client()
    models = (Activity, OutboxEvent, IdempotencyRecord)
    before = [model.objects.count() for model in models]
    version = Project.objects.values("event_sequence", "version", "board_revision").get(
        pk=context_targets["project"]
    )
    for target_type, target_id in context_targets.items():
        for domain in ("project", "team", "progress"):
            assert client.get(context_url(target_type, target_id, domain)).status_code == 200
        intent = "task_decomposition" if target_type == "task" else "risk_analysis"
        for _ in range(2):
            assert (
                client.post(
                    context_url(target_type, target_id),
                    {"action": "ai.analyze", "intent": intent},
                    format="json",
                ).status_code
                == 200
            )
    assert before == [model.objects.count() for model in models]
    assert (
        Project.objects.values("event_sequence", "version", "board_revision").get(
            pk=context_targets["project"]
        )
        == version
    )
