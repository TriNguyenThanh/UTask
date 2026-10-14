import io

import pytest

from apps.collaboration.models import Attachment
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_deep_json_upload_remains_pending_without_receipt_or_audit(
    created_project, client_for, actors, settings, monkeypatch
):
    body = ("[" * 1500 + "0" + "]" * 1500).encode()
    stream = io.BytesIO(body)

    class StorageClient:
        def generate_presigned_url(self, operation, **kwargs):
            assert operation == "put_object" and kwargs["Params"]["IfNoneMatch"] == "*"
            return "https://storage.test/upload"

        def head_object(self, **kwargs):
            return {"ContentLength": len(body), "ContentType": "application/json", "ETag": "deep"}

        def get_object(self, **kwargs):
            assert kwargs["IfMatch"] == "deep"
            return {"Body": stream}

    settings.WORK_STORAGE_ADAPTER = "infrastructure.storage.R2Storage"
    settings.WORK_R2_ENDPOINT = "https://storage.test"
    settings.WORK_R2_ACCESS_KEY = "offline-test-access"
    settings.WORK_R2_SECRET_KEY = "offline-test-secret"
    settings.WORK_R2_BUCKET = "test-bucket"
    monkeypatch.setattr("infrastructure.storage.boto3.client", lambda *a, **k: StorageClient())
    leader = client_for(actors["leader"])
    route = f"/api/v1/projects/{created_project['id']}/attachments/"
    allocated = leader.post(
        route + "presigned-url/",
        {"file_name": "nested.json", "file_size": len(body), "content_type": "application/json"},
        format="json",
    )
    assert allocated.status_code == 200
    attachment_id = allocated.json()["data"]["attachment_id"]
    row_before = Attachment.objects.filter(pk=attachment_id).values().get()
    before = effect_state(created_project["id"])
    reply = leader.post(
        route,
        {"attachment_id": attachment_id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="nested-json-confirm",
    )
    assert reply.status_code == 422 and reply.json()["error"]["code"] == "VALIDATION_ERROR"
    assert stream.closed
    assert Attachment.objects.filter(pk=attachment_id).values().get() == row_before
    assert effect_state(created_project["id"]) == before
    assert leader.get(route).json()["data"] == []
