import io
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest

from common.json_validation import MAX_JSON_NESTING_DEPTH
from infrastructure.storage import R2Storage


@pytest.mark.unit
def test_boto3_conditional_put_presign_signs_required_headers(monkeypatch, settings):
    settings.WORK_R2_BUCKET = "tests"
    client = boto3.client(
        "s3",
        endpoint_url="https://r2.example.test",
        aws_access_key_id="offline-test-only",
        aws_secret_access_key="offline-test-only",
        region_name="auto",
    )
    monkeypatch.setattr(R2Storage, "client", lambda self: client)
    row = SimpleNamespace(storage_key="work/test/key", file_size=10, content_type="text/plain")
    url, headers = R2Storage().presign(row)
    signed = parse_qs(urlsplit(url).query)["X-Amz-SignedHeaders"][0]
    assert "if-none-match" in signed and "content-type" in signed and "content-length" in signed
    assert headers["If-None-Match"] == "*"


_TOO_DEEP_JSON = b"[" * (MAX_JSON_NESTING_DEPTH + 1) + b"0" + b"]" * (MAX_JSON_NESTING_DEPTH + 1)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body,valid",
    [(b'{"ok":true}', True), (b"not json!!", False), (_TOO_DEEP_JSON, False)],
)
def test_storage_inspect_checks_content_bytes_outside_transaction(
    monkeypatch, settings, body, valid
):
    settings.WORK_R2_BUCKET = "tests"

    class Client:
        def head_object(self, **kwargs):
            return {
                "ContentLength": len(body),
                "ContentType": "application/json",
                "ETag": "test-etag",
            }

        def get_object(self, **kwargs):
            assert kwargs["IfMatch"] == "test-etag"
            return {"Body": io.BytesIO(body)}

    monkeypatch.setattr(R2Storage, "client", lambda self: Client())
    row = SimpleNamespace(
        storage_key="work/test/key", file_size=len(body), content_type="application/json"
    )
    assert R2Storage().inspect(row).valid_content is valid
