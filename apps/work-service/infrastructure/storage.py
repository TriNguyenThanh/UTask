import json
from dataclasses import dataclass

import boto3
import filetype
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils.module_loading import import_string

from common.errors import WorkError


@dataclass(frozen=True)
class ObjectFacts:
    size: int
    content_type: str
    valid_content: bool


class R2Storage:
    def client(self):
        names = ["WORK_R2_ENDPOINT", "WORK_R2_ACCESS_KEY", "WORK_R2_SECRET_KEY", "WORK_R2_BUCKET"]
        if any(not getattr(settings, name, "") for name in names):
            raise WorkError(
                "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tệp tin hiện không khả dụng.", 503
            )
        return boto3.client(
            "s3",
            endpoint_url=settings.WORK_R2_ENDPOINT,
            aws_access_key_id=settings.WORK_R2_ACCESS_KEY,
            aws_secret_access_key=settings.WORK_R2_SECRET_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=5,
                retries={"max_attempts": 1},
            ),
        )

    def presign(self, attachment):
        headers = {
            "Content-Type": attachment.content_type,
            "Content-Length": str(attachment.file_size),
            "If-None-Match": "*",
        }
        try:
            url = self.client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.WORK_R2_BUCKET,
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
            raise WorkError(
                "STORAGE_UNAVAILABLE", "Không thể tạo đường dẫn tải lên tệp tin.", 503
            ) from exc

    def inspect(self, attachment):
        try:
            client = self.client()
            head = client.head_object(Bucket=settings.WORK_R2_BUCKET, Key=attachment.storage_key)
            size, kind = head["ContentLength"], head["ContentType"]
            if size != attachment.file_size or kind != attachment.content_type:
                return ObjectFacts(size, kind, False)
            reply = client.get_object(
                Bucket=settings.WORK_R2_BUCKET, Key=attachment.storage_key, IfMatch=head["ETag"]
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
                        json.loads(text)
                    valid = True
                except (ValueError, UnicodeError, RecursionError):
                    pass
            else:
                valid = filetype.guess_mime(body) == kind
            return ObjectFacts(size, kind, valid)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code"))
            raise WorkError(
                "UPLOAD_NOT_FOUND"
                if code in {"404", "NoSuchKey", "NotFound"}
                else "STORAGE_UNAVAILABLE",
                "Không thể kiểm tra tệp tin đã tải lên.",
                404 if code in {"404", "NoSuchKey", "NotFound"} else 503,
            ) from exc
        except BotoCoreError as exc:
            raise WorkError(
                "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tệp tin hiện không khả dụng.", 503
            ) from exc

    def download(self, attachment):
        try:
            return self.client().generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.WORK_R2_BUCKET,
                    "Key": attachment.storage_key,
                    "ResponseContentDisposition": "attachment",
                    "ResponseContentType": "application/octet-stream",
                },
                ExpiresIn=300,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError) as exc:
            raise WorkError(
                "STORAGE_UNAVAILABLE", "Không thể tạo đường dẫn tải xuống tệp tin.", 503
            ) from exc

    def delete(self, key):
        try:
            self.client().delete_object(Bucket=settings.WORK_R2_BUCKET, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise WorkError(
                "STORAGE_UNAVAILABLE", "Không thể xóa tệp tin khỏi hệ thống lưu trữ.", 503
            ) from exc


def storage_client():
    return import_string(
        getattr(settings, "WORK_STORAGE_ADAPTER", "infrastructure.storage.R2Storage")
    )()
