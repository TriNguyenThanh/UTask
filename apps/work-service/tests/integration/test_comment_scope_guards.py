import pytest
from django.utils import timezone

from apps.collaboration.models import Comment
from apps.projects.models import Project
from apps.tasks.models import Task
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("proof", ["missing", "wrong-type"])
def test_teacher_feedback_requires_verified_scope_from_adapter(
    task_api, actors, client_for, classroom, monkeypatch, proof
):
    _, _, create = task_api
    task = create()
    if proof == "missing":
        monkeypatch.delattr(classroom, "teacher_feedback_scope")
    else:
        monkeypatch.setattr(
            classroom, "teacher_feedback_scope", staticmethod(lambda project, actor: {})
        )
    before = effect_state(task["project_id"])
    reply = client_for(actors["teacher"]).post(
        "/comments/",
        {"task_id": task["id"], "content_html": "<p>Feedback</p>"},
        format="json",
    )
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert not Comment.objects.exists() and effect_state(task["project_id"]) == before


@pytest.mark.parametrize("subject", ["task", "project"])
def test_archived_subject_comment_creation_rolls_back_before_audit(task_api, subject):
    leader, _, create = task_api
    task = create()
    if subject == "task":
        Task.objects.filter(pk=task["id"]).update(archived_at=timezone.now())
    else:
        Project.objects.filter(pk=task["project_id"]).update(archived_at=timezone.now())
    before = effect_state(task["project_id"])
    body = {
        "task_id" if subject == "task" else "project_id": task["id"]
        if subject == "task"
        else task["project_id"],
        "content_html": "<p>Denied</p>",
    }
    reply = leader.post("/comments/", body, format="json")
    assert reply.status_code == 400, reply.content
    assert not Comment.objects.exists() and effect_state(task["project_id"]) == before
