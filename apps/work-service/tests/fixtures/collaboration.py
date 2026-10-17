from uuid import UUID

import pytest

from apps.collaboration.models import Attachment


@pytest.fixture
def project_upload(created_project, actors, client_for, storage):
    route = f"/projects/{created_project['id']}/attachments/"
    uploader = client_for(actors["member"])
    reply = uploader.post(
        route + "presigned-url/",
        {"file_name": "../design.txt", "file_size": 10, "content_type": "text/plain"},
        format="json",
    )
    assert reply.status_code == 200, reply.content
    row = Attachment.objects.get(pk=reply.json()["data"]["attachment_id"])
    assert row.project_id == UUID(created_project["id"]) and row.task_id is None
    assert row.uploaded_by_user_id == actors["member"] and row.file_name == "design.txt"
    return uploader, route, row


def pending(leader, route):
    reply = leader.post(
        route + "presigned-url/",
        {"file_name": "safe.txt", "file_size": 10, "content_type": "text/plain"},
        format="json",
    )
    assert reply.status_code == 200, reply.content
    return Attachment.objects.get(pk=reply.json()["data"]["attachment_id"])


@pytest.fixture
def pending_file(task_api, storage):
    leader, _, create = task_api
    task = create()
    route = f"/tasks/{task['id']}/attachments/"
    return leader, task, route, pending(leader, route)
