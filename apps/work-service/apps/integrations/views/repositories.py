from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.integrations.serializers.repositories import (
    DisconnectRepositorySerializer,
    RepositoryInputSerializer,
    RepositorySerializer,
)
from apps.integrations.services.repositories import repository_data, select_repository
from apps.messaging.services.receipts import receipt_scope, require_key
from apps.projects.queries.projects import visible_project
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

REPOSITORY = envelope_schema("RepositoryEnvelope", RepositorySerializer)


KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER)


class RepositoryView(GenericAPIView):
    serializer_class = RepositoryInputSerializer

    @extend_schema(responses={200: REPOSITORY, **ERRORS})
    def get(self, request, project_id):
        return success_response(
            repository_data(visible_project(request.user, project_id)),
            message="Đã lấy thông tin kết nối kho mã nguồn của dự án.",
        )

    @extend_schema(
        request=RepositoryInputSerializer,
        parameters=[KEY],
        responses={202: REPOSITORY, **ERRORS, 410: ERRORS[400], 429: ERRORS[400]},
    )
    def post(self, request, project_id):
        visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        key = (
            require_key(request)
            if request.headers.get("Idempotency-Key")
            else payload["operation_id"]
        )
        return select_repository(
            request.user,
            project_id,
            payload,
            receipt_scope(request, key),
            request.headers.get("Authorization", ""),
        )

    @extend_schema(
        request=DisconnectRepositorySerializer,
        parameters=[KEY],
        responses={202: REPOSITORY, **ERRORS, 410: ERRORS[400], 429: ERRORS[400]},
    )
    def delete(self, request, project_id):
        from apps.integrations.services.operations import start_operation

        visible_project(request.user, project_id, for_write=True)
        serializer = DisconnectRepositorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        key = (
            require_key(request)
            if request.headers.get("Idempotency-Key")
            else payload["operation_id"]
        )
        return start_operation(
            request.user,
            project_id,
            payload,
            receipt_scope(request, key),
            request.headers.get("Authorization", ""),
            action="DISCONNECT",
        )
