from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.collaboration.queries import subject_attachments
from apps.collaboration.serializers import (
    AttachmentSerializer,
    ConfirmAttachmentSerializer,
    DownloadSerializer,
    PresignInputSerializer,
    PresignSerializer,
)
from apps.collaboration.services.attachments import (
    confirm_attachment,
    get_attachment,
    presign_attachment,
    remove_attachment,
)
from apps.messaging.services import receipt_scope, require_key
from apps.projects.queries import visible_project
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import KEY_PARAMETER
from apps.tasks.queries import visible_task
from common.errors import WorkError
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import envelope_schema
from infrastructure.storage import storage_client

ATTACHMENT = envelope_schema("AttachmentEnvelope", AttachmentSerializer)


def resolve_subject(request, task_id=None, project_id=None, *, write=False):
    return (
        visible_task(request.user, task_id, for_write=write)
        if task_id
        else visible_project(request.user, project_id, for_write=write)
    )


class PresignView(GenericAPIView):
    serializer_class = PresignInputSerializer

    @extend_schema(
        request=PresignInputSerializer,
        responses={200: envelope_schema("PresignEnvelope", PresignSerializer), **ERRORS},
    )
    def post(self, request, task_id=None, project_id=None):
        subject = resolve_subject(request, task_id, project_id, write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return presign_attachment(request.user, subject, serializer.validated_data)


class AttachmentListConfirmView(GenericAPIView):
    serializer_class = ConfirmAttachmentSerializer

    @extend_schema(
        parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)],
        responses={
            200: envelope_schema(
                "AttachmentsEnvelope", AttachmentSerializer, many=True, paginated=True
            ),
            **ERRORS,
        },
    )
    def get(self, request, task_id=None, project_id=None):
        resolve_subject(request, task_id, project_id)
        rows = subject_attachments(task_id=task_id, project_id=project_id)
        rows, meta = paginate(
            rows,
            request.query_params,
            scope={
                "actor": str(request.user.id),
                "task": str(task_id),
                "project": str(project_id),
                "attachments": True,
            },
        )
        return success_response(
            AttachmentSerializer(rows, many=True).data,
            meta=meta,
            message="Đã tải danh sách tệp đính kèm.",
        )

    @extend_schema(
        request=ConfirmAttachmentSerializer,
        parameters=[KEY_PARAMETER],
        responses={200: ATTACHMENT, **ERRORS},
    )
    def post(self, request, task_id=None, project_id=None):
        subject = resolve_subject(request, task_id, project_id, write=True)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        return confirm_attachment(
            request.user, subject, payload["attachment_id"], receipt_scope(request, key), payload
        )


class AttachmentDownloadView(GenericAPIView):
    serializer_class = DownloadSerializer

    @extend_schema(
        responses={200: envelope_schema("DownloadEnvelope", DownloadSerializer), **ERRORS}
    )
    def get(self, request, attachment_id, task_id=None, project_id=None):
        subject = resolve_subject(request, task_id, project_id)
        row = get_attachment(subject, attachment_id)
        if row.status != "CONFIRMED":
            raise WorkError("INVALID_OPERATION", "Tệp tin chưa được xác nhận tải lên hoàn tất.")
        return success_response(
            {"download_url": storage_client().download(row), "expires_in": 300},
            message="Đã tạo đường dẫn tải xuống tệp đính kèm.",
        )


class AttachmentDeleteView(GenericAPIView):
    serializer_class = AttachmentSerializer

    @extend_schema(request=None, responses={200: ATTACHMENT, **ERRORS})
    def delete(self, request, attachment_id, task_id=None, project_id=None):
        subject = resolve_subject(request, task_id, project_id, write=True)
        return remove_attachment(request.user, subject, attachment_id)
