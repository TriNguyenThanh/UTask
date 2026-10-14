from uuid import uuid4

import pytest
import requests
from django.conf import settings

from infrastructure.storage import R2Storage

pytestmark = [pytest.mark.external]


def test_r2_real_presign_put_content_confirm_download_and_cleanup():
    missing = [
        name
        for name in [
            "WORK_R2_ENDPOINT",
            "WORK_R2_ACCESS_KEY",
            "WORK_R2_SECRET_KEY",
            "WORK_R2_BUCKET",
        ]
        if not getattr(settings, name, "")
    ]
    if missing:
        pytest.fail("R2 integration chưa có cấu hình Work riêng: " + ",".join(missing))
    from types import SimpleNamespace

    body = b"work-integration-only"
    row = SimpleNamespace(
        storage_key="work/integration-tests/" + uuid4().hex,
        file_size=len(body),
        content_type="text/plain",
    )
    storage = R2Storage()
    client = storage.client()
    try:
        url, headers = storage.presign(row)
        put = requests.put(url, data=body, headers=headers, timeout=(5, 15))
        assert put.status_code in {200, 201}, "R2 PUT failed; signed URL intentionally omitted"
        second = requests.put(url, data=body, headers=headers, timeout=(5, 15))
        assert second.status_code in {409, 412}, "R2 did not enforce conditional PUT"
        facts = storage.inspect(row)
        assert (
            facts.size == len(body) and facts.content_type == "text/plain" and facts.valid_content
        )
        download = storage.download(row)
        get = requests.get(download, timeout=(5, 15))
        assert get.status_code == 200 and get.content == body
    finally:
        client.delete_object(Bucket=settings.WORK_R2_BUCKET, Key=row.storage_key)
