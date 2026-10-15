import io
from types import SimpleNamespace

import pytest

from common.errors import WorkError
from infrastructure.storage import R2Storage

pytestmark = pytest.mark.unit


@pytest.fixture
def configured_storage(settings):
    settings.WORK_R2_ENDPOINT = "https://storage.test"
    settings.WORK_R2_ACCESS_KEY = "offline-test-access"
    settings.WORK_R2_SECRET_KEY = "offline-test-secret"
    settings.WORK_R2_BUCKET = "test-bucket"


def test_storage_client_requires_complete_configuration_before_sdk(
    configured_storage, settings, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        "infrastructure.storage.boto3.client",
        lambda service, **kwargs: calls.append((service, kwargs)) or object(),
    )
    settings.WORK_R2_BUCKET = ""
    with pytest.raises(WorkError) as error:
        R2Storage().client()
    assert error.value.code == "STORAGE_UNAVAILABLE" and calls == []
    settings.WORK_R2_BUCKET = "test-bucket"
    R2Storage().client()
    assert len(calls) == 1 and calls[0][0] == "s3"
    assert calls[0][1]["endpoint_url"] == "https://storage.test"
    assert calls[0][1]["config"].signature_version == "s3v4"


@pytest.mark.parametrize("mismatch", ["size", "type", "body-length"])
def test_object_inspection_rejects_head_or_download_mismatch(
    configured_storage, monkeypatch, mismatch
):
    fetched = []
    body = b"valid text"

    class Client:
        def head_object(self, **kwargs):
            return {
                "ContentLength": len(body) + 1 if mismatch == "size" else len(body),
                "ContentType": "image/png" if mismatch == "type" else "text/plain",
                "ETag": "stable",
            }

        def get_object(self, **kwargs):
            fetched.append(kwargs)
            return {"Body": io.BytesIO(body[:-1] if mismatch == "body-length" else body)}

    monkeypatch.setattr("infrastructure.storage.boto3.client", lambda *args, **kwargs: Client())
    row = SimpleNamespace(storage_key="test/key", file_size=len(body), content_type="text/plain")
    facts = R2Storage().inspect(row)
    assert facts.valid_content is False
    assert bool(fetched) == (mismatch == "body-length")
    if fetched:
        assert fetched[0]["IfMatch"] == "stable"


@pytest.mark.parametrize(
    "kind,body",
    [("text/plain", "Nội dung".encode()), ("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)],
)
def test_storage_inspection_accepts_verified_text_or_binary_mime(
    configured_storage, monkeypatch, kind, body
):
    stream = io.BytesIO(body)

    class Client:
        def head_object(self, **kwargs):
            return {"ContentLength": len(body), "ContentType": kind, "ETag": "stable"}

        def get_object(self, **kwargs):
            return {"Body": stream}

    monkeypatch.setattr("infrastructure.storage.boto3.client", lambda *args, **kwargs: Client())
    row = SimpleNamespace(storage_key="test/key", file_size=len(body), content_type=kind)
    facts = R2Storage().inspect(row)
    assert facts.valid_content is True and facts.size == len(body) and facts.content_type == kind
    assert stream.closed
