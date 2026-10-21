from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.integrations.queries import task_github_links
from apps.integrations.serializers.links import (
    GitHubLinkSerializer,
    LinkInputSerializer,
    UnlinkedSerializer,
)
from apps.integrations.services.links import confirm_link, manual_link, unlink
from apps.messaging.services.receipts import receipt_scope, require_key
from apps.tasks.queries import visible_task
from common.responses import success_response
from common.serializers import StrictInputSerializer
from config.api_documentation import ERRORS, envelope_schema

LINK = envelope_schema("GitHubLinkEnvelope", GitHubLinkSerializer)


LINKS = envelope_schema("GitHubLinksEnvelope", GitHubLinkSerializer, many=True)


KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER)


class LinkListCreateView(GenericAPIView):
    serializer_class = LinkInputSerializer

    @extend_schema(responses={200: LINKS, **ERRORS})
    def get(self, request, task_id):
        rows = task_github_links(request.user, task_id)
        return success_response(
            GitHubLinkSerializer(rows, many=True).data,
            message="Đã lấy danh sách liên kết GitHub của công việc.",
        )

    @extend_schema(
        request=LinkInputSerializer,
        parameters=[KEY],
        responses={201: LINK, **ERRORS, 410: ERRORS[400], 429: ERRORS[400]},
    )
    def post(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = (
            receipt_scope(request, require_key(request))
            if request.headers.get("Idempotency-Key")
            else None
        )
        return manual_link(
            request.user,
            task_id,
            serializer.validated_data,
            request.headers.get("Authorization", ""),
            scope,
        )


class LinkConfirmView(GenericAPIView):
    serializer_class = StrictInputSerializer

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
        ],
        responses={200: LINK, **ERRORS},
    )
    def post(self, request, task_id, link_id):
        visible_task(request.user, task_id, for_write=True)
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        return confirm_link(
            request.user, task_id, link_id, receipt_scope(request, require_key(request))
        )


class LinkDetailView(GenericAPIView):
    serializer_class = StrictInputSerializer

    @extend_schema(
        request=None,
        responses={200: envelope_schema("UnlinkedEnvelope", UnlinkedSerializer), **ERRORS},
    )
    def delete(self, request, task_id, link_id):
        visible_task(request.user, task_id, for_write=True)
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        return unlink(request.user, task_id, link_id)
