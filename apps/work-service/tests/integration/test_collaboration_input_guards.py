import pytest

from apps.collaboration.models import Attachment, Comment
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("name", [".", "..", "bad\x01name"])
def test_presign_rejects_invalid_sanitized_filename_without_allocation(task_api, name):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.post(
        f"/tasks/{task['id']}/attachments/presigned-url/",
        {"file_name": name, "file_size": 10, "content_type": "text/plain"},
        format="json",
    )
    assert reply.status_code == 400 and reply.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not Attachment.objects.exists() and effect_state(task["project_id"]) == before


def test_teacher_external_recipient_requires_recipient_scope_adapter(task_api, actors, client_for):
    _, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = client_for(actors["teacher"]).post(
        "/comments/",
        {
            "task_id": task["id"],
            "content_html": "<p>Teacher</p>",
            "mentioned_user_ids": [str(actors["outsider"])],
        },
        format="json",
    )
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"
    assert not Comment.objects.exists() and effect_state(task["project_id"]) == before


@pytest.mark.parametrize(
    "kind,ref",
    [
        ("PULL_REQUEST", "0"),
        ("PULL_REQUEST", "abc"),
        ("BRANCH", "feature/work"),
        ("COMMIT", "abc123"),
    ],
)
def test_github_reference_input_canonicalization_by_ref_kind(github, kind, ref):
    _, leader, _, task = github
    before = effect_state(task.project_id)
    reply = leader.post(
        f"/tasks/{task.pk}/github-links/",
        {"link_type": kind, "github_ref_id": ref},
        format="json",
        HTTP_IDEMPOTENCY_KEY="kind-reference",
    )
    assert reply.status_code == (400 if kind == "PULL_REQUEST" else 201), reply.content
    if kind == "PULL_REQUEST":
        assert effect_state(task.project_id) == before
    else:
        assert (
            reply.json()["data"]["link_type"] == kind
            and reply.json()["data"]["github_ref_id"] == ref
        )
