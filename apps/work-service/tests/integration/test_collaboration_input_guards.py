import pytest

from apps.collaboration.models import Comment
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_teacher_external_recipient_requires_recipient_scope_adapter(task_api, actors, client_for):
    _, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = client_for(actors["teacher"]).post(
        "/api/v1/comments/",
        {
            "task_id": task["id"],
            "content_html": "<p>Teacher</p>",
            "mentioned_user_ids": [str(actors["outsider"])],
        },
        format="json",
    )
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert not Comment.objects.exists() and effect_state(task["project_id"]) == before
