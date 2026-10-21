from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.collaboration.models import Comment, CommentMention
from apps.messaging.models import OutboxEvent
from apps.projects.models import ProjectMember, State
from apps.tasks.models import Task, TaskAssignment
from apps.tasks.tasks import scan_deadlines
from apps.tasks.views.notification_resolution import resolve_notification
from tests.event_contracts import assert_event_contract
from tests.fixtures.transactions import reject_outbox_event as reject_outbox_event

pytestmark = pytest.mark.django_db
ROUTE = "/api/v1/internal/notifications/resolve"


def test_internal_token_and_validation(settings):
    client = APIClient()
    settings.NOTIFICATION_SERVICE_TOKEN = ""
    assert client.post(ROUTE, {}, format="json").status_code == 403
    settings.NOTIFICATION_SERVICE_TOKEN = "secret"
    assert client.post(ROUTE, {}, format="json", HTTP_X_SERVICE_TOKEN="wrong").status_code == 403
    assert client.post(ROUTE, {}, format="json", HTTP_X_SERVICE_TOKEN="secret").status_code == 400


def test_assignment_and_current_access(task_api, actors, settings):
    _, _, create = task_api
    row = create()
    task = Task.objects.get(pk=row["id"])
    event = OutboxEvent.objects.get(event_type="task.assigned")
    assert_event_contract(event)
    assert event.data["data"] == {
        "task_id": row["id"],
        "actor_user_id": str(actors["leader"]),
        "recipient_ids": [str(actors["member"])],
    }
    settings.NOTIFICATION_SERVICE_TOKEN = "secret"
    request = {
        "user_id": str(actors["member"]),
        "event_type": event.event_type,
        "project_id": str(task.project_id),
        "data": event.data["data"],
    }
    reply = APIClient().post(ROUTE, request, format="json", HTTP_X_SERVICE_TOKEN="secret")
    assert reply.status_code == 200
    assert reply.json()["eligible"] is True
    assert reply.json()["target"]["issueKey"] == row["code"]
    assert not resolve_notification(
        actors["outsider"], event.event_type, task.project_id, event.data["data"]
    )["eligible"]
    TaskAssignment.objects.filter(task=task).delete()
    assert not resolve_notification(
        actors["member"], event.event_type, task.project_id, event.data["data"]
    )["eligible"]


def test_assignment_changes_only_new_users_excluding_actor(task_api, actors):
    leader, _, create = task_api
    row = create(assignee_ids=[str(actors["leader"])])
    assert not OutboxEvent.objects.filter(event_type="task.assigned").exists()
    route = f"/tasks/{row['id']}/"
    patch = {
        "expected_version": row["version"],
        "assignee_ids": [str(actors["member"]), str(actors["leader"])],
    }
    response = leader.patch(route, patch, format="json")
    assert response.status_code == 200, response.content
    event = OutboxEvent.objects.get(event_type="task.assigned")
    assert_event_contract(event)
    assert event.data["data"]["recipient_ids"] == [str(actors["member"])]
    patch["expected_version"] = response.json()["data"]["version"]
    assert leader.patch(route, patch, format="json").status_code == 200
    assert OutboxEvent.objects.filter(event_type="task.assigned").count() == 1


def test_mentions_feedback_deleted_and_cross_project(task_api, actors):
    _, _, create = task_api
    task = Task.objects.get(pk=create()["id"])
    comment = Comment.objects.create(
        task=task, user_id=actors["leader"], content_html="<p>Test</p>", content_stripped="Test"
    )
    data = {"comment_id": str(comment.pk)}
    args = (actors["member"], "comment.mentions.added", task.project_id, data)
    assert not resolve_notification(*args)["eligible"]
    CommentMention.objects.create(comment=comment, user_id=actors["member"])
    assert resolve_notification(*args)["eligible"]
    assert not resolve_notification(actors["member"], "comment.mentions.added", uuid4(), data)[
        "eligible"
    ]
    assert not resolve_notification(
        actors["member"], "teacher.feedback.added", task.project_id, data
    )["eligible"]
    comment.deleted_at = timezone.now()
    comment.save()
    assert not resolve_notification(*args)["eligible"]


def test_deadline_revision_terminal_and_membership(task_api, actors):
    _, _, create = task_api
    day = timezone.localdate(timezone=timezone.get_fixed_timezone(420))
    task = Task.objects.get(pk=create(due_date=day.isoformat())["id"])
    scan_deadlines()
    event = OutboxEvent.objects.get(event_type="task.deadline.reminder")
    assert_event_contract(event)
    args = (actors["member"], event.event_type, task.project_id, event.data["data"])
    assert resolve_notification(*args)["eligible"]
    forged = {**event.data["data"], "deadline_revision": "wrong"}
    assert not resolve_notification(actors["member"], event.event_type, task.project_id, forged)[
        "eligible"
    ]
    task.due_date = day + timedelta(days=3)
    task.save()
    assert not resolve_notification(*args)["eligible"]
    task.due_date = day
    task.state = State.objects.filter(project=task.project, group="COMPLETED").first()
    task.completed_at = timezone.now()
    task.save()
    assert not resolve_notification(*args)["eligible"]
    member = ProjectMember.objects.get(project=task.project, user_id=actors["member"])
    member.status, member.left_at = "LEFT", timezone.now()
    member.save()
    assert not resolve_notification(*args)["eligible"]


def test_transition_event_and_invalid_current_state(task_api, actors):
    leader, _, create = task_api
    row = create()
    target = State.objects.get(project_id=row["project_id"], group="COMPLETED")
    response = leader.patch(
        f"/tasks/{row['id']}/transition/",
        {"expected_version": 1, "target_state_id": str(target.pk)},
        format="json",
    )
    assert response.status_code == 200, response.content
    event = OutboxEvent.objects.get(event_type="task.transitioned")
    assert_event_contract(event)
    data = event.data["data"]
    assert data["actor_user_id"] == str(actors["leader"])
    assert data["recipient_ids"] == [str(actors["member"])]
    assert resolve_notification(actors["member"], event.event_type, row["project_id"], data)[
        "eligible"
    ]
    data["state_id"] = str(uuid4())
    assert not resolve_notification(actors["member"], event.event_type, row["project_id"], data)[
        "eligible"
    ]


def test_ai_create_assignment_and_replay(task_api, actors, ai):
    from apps.projects.models import Project
    from tests.fixtures.ai_proposals import backlog_payload

    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[2])
    ai(project.pk)
    body = backlog_payload(project)
    body["tasks"][0]["assignee_ids"] = [str(actors["member"])]
    response = leader.post(
        route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="assigned-ai"
    )
    assert response.status_code == 201, response.content
    event = OutboxEvent.objects.get(event_type="task.assigned")
    assert_event_contract(event)
    assert event.data["data"]["recipient_ids"] == [str(actors["member"])]
    assert (
        leader.post(
            route + "bulk-apply-ai/", body, format="json", HTTP_IDEMPOTENCY_KEY="assigned-ai"
        ).status_code
        == 201
    )
    assert OutboxEvent.objects.filter(event_type="task.assigned").count() == 1


@pytest.mark.django_db(transaction=True)
def test_assignment_event_failure_rolls_back_create(task_api, actors, reject_outbox_event):
    leader, route, _ = task_api
    with reject_outbox_event("task.assigned"):
        reply = leader.post(
            route,
            {"title": "Rollback assignment", "assignee_ids": [str(actors["member"])]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="assignment-failure",
        )
    assert reply.status_code == 500
    assert not Task.objects.exists()
    assert not OutboxEvent.objects.filter(event_type__in=["task.created", "task.assigned"]).exists()


def test_feedback_project_target_and_malformed_data(task_api, actors):
    _, _, create = task_api
    task = Task.objects.get(pk=create()["id"])
    comment = Comment.objects.create(
        project=task.project,
        user_id=actors["teacher"],
        content_html="<p>Review</p>",
        content_stripped="Review",
        is_teacher_feedback=True,
    )
    args = (actors["member"], "teacher.feedback.added", task.project_id)
    result = resolve_notification(*args, {"id": str(comment.pk)})
    assert result["eligible"]
    assert result["target"] == {"kind": "backlog", "projectId": str(task.project_id)}
    assert not resolve_notification(*args, {"id": "invalid"})["eligible"]
    assert not resolve_notification(
        actors["member"], "task.assigned", task.project_id, {"task_id": {"bad": "type"}}
    )["eligible"]


def test_batch_order_validation_revoked_and_project_query_cache(task_api, actors, settings):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _, _, create = task_api
    row = create()
    settings.NOTIFICATION_SERVICE_TOKEN = "secret"
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_TOKEN="secret")
    item = {
        "user_id": str(actors["member"]),
        "event_type": "task.assigned",
        "project_id": row["project_id"],
        "data": {"task_id": row["id"]},
    }
    denied = {**item, "data": {"task_id": str(uuid4())}}
    with CaptureQueriesContext(connection) as queries:
        response = client.post(ROUTE, {"items": [item, denied, item]}, format="json")
    assert response.status_code == 200
    assert [result["eligible"] for result in response.json()["results"]] == [True, False, True]
    project_reads = [query for query in queries if 'FROM "projects"' in query["sql"]]
    assert len(project_reads) == 1
    for items in [[], [item] * 101, [item, {**item, "user_id": "bad"}]]:
        response = client.post(ROUTE, {"items": items}, format="json")
        assert response.status_code == 400
    member = ProjectMember.objects.get(project_id=row["project_id"], user_id=actors["member"])
    member.status, member.left_at = "REMOVED", timezone.now()
    member.save()
    response = client.post(ROUTE, {"items": [item, item]}, format="json")
    assert [result["eligible"] for result in response.json()["results"]] == [False, False]
