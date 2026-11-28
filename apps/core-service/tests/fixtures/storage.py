"""In-memory R2Storage fake matching infrastructure.storage.R2Storage signatures."""

from __future__ import annotations

from typing import Any

import pytest

from common.errors import CoreAPIError
from infrastructure.storage import ObjectFacts


class InMemoryStorage:
    """In-memory fake for Cloudflare R2 attachment and avatar operations."""

    objects: dict[str, ObjectFacts] = {}
    missing_keys: set[str] = set()
    deletes: list[str] = []
    presigned: list[str] = []
    avatars: dict[str, dict[str, Any]] = {}
    presigned_avatars: list[tuple[str, str, int]] = []
    deleted_avatars: list[str] = []
    fail_on: dict[str, Exception] = {}

    @classmethod
    def reset(cls) -> None:
        cls.objects = {}
        cls.missing_keys = set()
        cls.deletes = []
        cls.presigned = []
        cls.avatars = {}
        cls.presigned_avatars = []
        cls.deleted_avatars = []
        cls.fail_on = {}

    @classmethod
    def put_object(
        cls,
        key: str,
        *,
        size: int,
        content_type: str,
        valid_content: bool = True,
    ) -> ObjectFacts:
        facts = ObjectFacts(size=size, content_type=content_type, valid_content=valid_content)
        cls.objects[key] = facts
        cls.missing_keys.discard(key)
        return facts

    @classmethod
    def put_avatar(cls, key: str, *, content_type: str, content_length: int) -> dict[str, Any]:
        meta = {"ContentType": content_type, "ContentLength": content_length}
        cls.avatars[key] = meta
        return meta

    def _maybe_fail(self, operation: str) -> None:
        error = self.fail_on.get(operation)
        if error is not None:
            raise error

    # --- Attachment operations (Work / Classroom Materials) ---

    def presign(self, attachment) -> tuple[str, dict[str, str]]:
        self._maybe_fail("presign")
        self.presigned.append(attachment.storage_key)
        headers = {
            "Content-Type": attachment.content_type,
            "Content-Length": str(attachment.file_size),
            "If-None-Match": "*",
        }
        return f"https://storage.test/put/{attachment.pk}", headers

    def inspect(self, attachment) -> ObjectFacts:
        self._maybe_fail("inspect")
        if attachment.storage_key in self.missing_keys:
            raise CoreAPIError(
                "UPLOAD_NOT_FOUND",
                "Không thể kiểm tra tệp tin đã tải lên.",
                404,
            )
        return self.objects.get(
            attachment.storage_key,
            ObjectFacts(attachment.file_size, attachment.content_type, True),
        )

    def download(self, attachment) -> str:
        self._maybe_fail("download")
        return f"https://storage.test/get/{attachment.pk}"

    def delete(self, key: str) -> None:
        self._maybe_fail("delete")
        self.objects.pop(key, None)
        self.deletes.append(key)

    # --- Avatar operations (Identity) ---

    def presign_avatar(self, key: str, mime: str, size: int) -> str:
        self._maybe_fail("presign_avatar")
        self.presigned_avatars.append((key, mime, size))
        return f"https://storage.test/avatars/put/{key}"

    def head_avatar(self, key: str) -> dict[str, Any]:
        self._maybe_fail("head_avatar")
        if key not in self.avatars:
            raise CoreAPIError(
                "UPLOAD_NOT_FOUND",
                "Chưa tìm thấy ảnh tải lên.",
                status_code=404,
            )
        return dict(self.avatars[key])

    def delete_avatar(self, key: str) -> bool:
        self._maybe_fail("delete_avatar")
        self.deleted_avatars.append(key)
        return self.avatars.pop(key, None) is not None


FixtureStorage = InMemoryStorage


@pytest.fixture
def storage(settings):
    """Configure Core Service to use the isolated InMemoryStorage adapter."""
    adapter_path = "tests.fixtures.storage.InMemoryStorage"
    settings.CORE_STORAGE_ADAPTER = adapter_path
    settings.WORK_STORAGE_ADAPTER = adapter_path
    InMemoryStorage.reset()
    yield InMemoryStorage
    InMemoryStorage.reset()
