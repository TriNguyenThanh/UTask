"""Unified Cloudflare R2 (S3-compatible) storage adapter for Avatars, Attachments, and Materials."""

import json
import logging
from dataclasses import dataclass

import boto3
import filetype
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils.module_loading import import_string

from common.errors import CoreAPIError
from common.json_validation import has_excessive_json_nesting

logger = logging.getLogger("core.storage")


@dataclass(frozen=True)
class ObjectFacts:
    size: int
    content_type: str
    valid_content: bool


class R2Storage:
    """Single S3/R2 storage client shared across Identity avatars and Work attachments."""

    def _resolve_config(self, *, namespace: str = "core"):
        if namespace == "avatar":
            endpoint = getattr(settings, "IDENTITY_R2_ENDPOINT", "") or getattr(
                settings, "CORE_R2_ENDPOINT", ""
            )
            access_key = getattr(settings, "IDENTITY_R2_ACCESS_KEY", "") or getattr(
                settings, "CORE_R2_ACCESS_KEY", ""
            )
            secret_key = getattr(settings, "IDENTITY_R2_SECRET_KEY", "") or getattr(
                settings, "CORE_R2_SECRET_KEY", ""
            )
            bucket = getattr(settings, "IDENTITY_R2_BUCKET", "") or getattr(
                settings, "CORE_R2_BUCKET", ""
            )
        else:
            endpoint = getattr(settings, "WORK_R2_ENDPOINT", "") or getattr(
                settings, "CORE_R2_ENDPOINT", ""
            )
            access_key = getattr(settings, "WORK_R2_ACCESS_KEY", "") or getattr(
                settings, "CORE_R2_ACCESS_KEY", ""
            )
            secret_key = getattr(settings, "WORK_R2_SECRET_KEY", "") or getattr(
                settings, "CORE_R2_SECRET_KEY", ""
            )
            bucket = getattr(settings, "WORK_R2_BUCKET", "") or getattr(
                settings, "CORE_R2_BUCKET", ""
            )
        if not all((endpoint, access_key, secret_key, bucket)):
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tệp tin hiện không khả dụng.", 503
            )
        return endpoint, access_key, secret_key, bucket

    def client(self, *, namespace: str = "core"):
        endpoint, access_key, secret_key, _bucket = self._resolve_config(namespace=namespace)
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=5,
                retries={"max_attempts": 1},
            ),
        )

    # --- Attachment operations (Work / Classroom Materials) ---

    def presign(self, attachment):
        _, _, _, bucket = self._resolve_config(namespace="attachment")
        headers = {
            "Content-Type": attachment.content_type,
            "Content-Length": str(attachment.file_size),
            "If-None-Match": "*",
        }
        try:
            url = self.client(namespace="attachment").generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": bucket,
                    "Key": attachment.storage_key,
                    "ContentType": attachment.content_type,
                    "ContentLength": attachment.file_size,
                    "IfNoneMatch": "*",
                },
                ExpiresIn=900,
                HttpMethod="PUT",
            )
            return url, headers
        except (BotoCoreError, ClientError) as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể tạo đường dẫn tải lên tệp tin.", 503
            ) from exc

    def inspect(self, attachment):
        _, _, _, bucket = self._resolve_config(namespace="attachment")
        try:
            client = self.client(namespace="attachment")
            head = client.head_object(Bucket=bucket, Key=attachment.storage_key)
            size, kind = head["ContentLength"], head["ContentType"]
            if size != attachment.file_size or kind != attachment.content_type:
                return ObjectFacts(size, kind, False)
            reply = client.get_object(
                Bucket=bucket, Key=attachment.storage_key, IfMatch=head["ETag"]
            )
            stream = reply["Body"]
            try:
                body = stream.read(26214401)
            finally:
                stream.close()
            if len(body) != size:
                return ObjectFacts(size, kind, False)
            valid = False
            if kind in {"text/plain", "application/json"}:
                try:
                    text = body.decode("utf-8")
                    if kind == "application/json":
                        if has_excessive_json_nesting(json.loads(text)):
                            return ObjectFacts(size, kind, False)
                    valid = True
                except (ValueError, UnicodeError, RecursionError):
                    pass
            else:
                valid = filetype.guess_mime(body) == kind
            return ObjectFacts(size, kind, valid)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code"))
            raise CoreAPIError(
                "UPLOAD_NOT_FOUND"
                if code in {"404", "NoSuchKey", "NotFound"}
                else "STORAGE_UNAVAILABLE",
                "Không thể kiểm tra tệp tin đã tải lên.",
                404 if code in {"404", "NoSuchKey", "NotFound"} else 503,
            ) from exc
        except BotoCoreError as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tệp tin hiện không khả dụng.", 503
            ) from exc

    def download(self, attachment):
        _, _, _, bucket = self._resolve_config(namespace="attachment")
        try:
            return self.client(namespace="attachment").generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": attachment.storage_key,
                    "ResponseContentDisposition": "attachment",
                    "ResponseContentType": "application/octet-stream",
                },
                ExpiresIn=300,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError) as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể tạo đường dẫn tải xuống tệp tin.", 503
            ) from exc

    def delete(self, key):
        _, _, _, bucket = self._resolve_config(namespace="attachment")
        try:
            self.client(namespace="attachment").delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể xóa tệp tin khỏi hệ thống lưu trữ.", 503
            ) from exc

    # --- Avatar operations (Identity) ---

    def presign_avatar(self, key: str, mime: str, size: int) -> str:
        _, _, _, bucket = self._resolve_config(namespace="avatar")
        try:
            return self.client(namespace="avatar").generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ContentType": mime,
                    "ContentLength": size,
                },
                ExpiresIn=300,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể tạo URL tải ảnh.", status_code=503
            ) from exc

    def head_avatar(self, key: str):
        _, _, _, bucket = self._resolve_config(namespace="avatar")
        try:
            return self.client(namespace="avatar").head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                raise CoreAPIError(
                    "UPLOAD_NOT_FOUND", "Chưa tìm thấy ảnh tải lên.", status_code=404
                ) from exc
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể kiểm tra ảnh đã tải lên.", status_code=503
            ) from exc
        except BotoCoreError as exc:
            raise CoreAPIError(
                "STORAGE_UNAVAILABLE", "Không thể kiểm tra ảnh đã tải lên.", status_code=503
            ) from exc

    def delete_avatar(self, key: str) -> bool:
        try:
            _, _, _, bucket = self._resolve_config(namespace="avatar")
            self.client(namespace="avatar").delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                return False
            logger.warning("Avatar R2 object cleanup failed error=%s", type(exc).__name__)
            return False
        except (BotoCoreError, CoreAPIError) as exc:
            logger.warning("Avatar R2 object cleanup failed error=%s", type(exc).__name__)
            return False


def storage_client():
    return import_string(
        getattr(settings, "CORE_STORAGE_ADAPTER", "")
        or getattr(settings, "WORK_STORAGE_ADAPTER", "infrastructure.storage.R2Storage")
    )()
