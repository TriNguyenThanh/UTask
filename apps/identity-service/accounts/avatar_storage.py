"""R2's S3 API via boto3. No local success fallback or bespoke signing."""

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from common.errors import IdentityAPIError


class AvatarStorage:
    @staticmethod
    def client():
        return boto3.client(
            "s3",
            endpoint_url=settings.IDENTITY_R2_ENDPOINT,
            aws_access_key_id=settings.IDENTITY_R2_ACCESS_KEY,
            aws_secret_access_key=settings.IDENTITY_R2_SECRET_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=5,
                retries={"max_attempts": 1},
            ),
        )

    @classmethod
    def presign(cls, key, mime, size):
        try:
            return cls.client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.IDENTITY_R2_BUCKET,
                    "Key": key,
                    "ContentType": mime,
                    "ContentLength": size,
                },
                ExpiresIn=300,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError) as exc:
            raise IdentityAPIError(
                "STORAGE_UNAVAILABLE", "Không thể tạo URL tải ảnh.", status_code=503
            ) from exc

    @classmethod
    def head(cls, key):
        try:
            return cls.client().head_object(Bucket=settings.IDENTITY_R2_BUCKET, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                raise IdentityAPIError(
                    "UPLOAD_NOT_FOUND", "Chưa tìm thấy ảnh tải lên.", status_code=404
                ) from exc
            raise IdentityAPIError(
                "STORAGE_UNAVAILABLE", "Không thể kiểm tra ảnh trên R2.", status_code=503
            ) from exc
        except BotoCoreError as exc:
            raise IdentityAPIError(
                "STORAGE_UNAVAILABLE", "Không thể kiểm tra ảnh trên R2.", status_code=503
            ) from exc
