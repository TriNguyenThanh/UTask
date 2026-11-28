"""Integration chỉ hỏi quyền đọc Project; Core không gọi GitHub tại đây."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated

from apps.integrations.serializers.repositories import (
    IntegrationAuthorizeInputSerializer,
    IntegrationAuthorizeResultSerializer,
)
from apps.projects.queries.projects import readable_project
from common.errors import CoreAPIError
from common.permissions import IntegrationCallerPermission
from common.responses import success_response
from common.views import InternalReadView
from config.api_documentation import ERRORS, envelope_schema


class ProjectReadAuthorizeView(InternalReadView):
    permission_classes = [IsAuthenticated, IntegrationCallerPermission]

    @extend_schema(
        operation_id="internal_integration_github_authorize",
        auth=[{"jwtAuth": [], "WorkServiceKey": []}],
        request=IntegrationAuthorizeInputSerializer,
        responses={
            200: envelope_schema(
                "IntegrationAuthorizeEnvelope", IntegrationAuthorizeResultSerializer
            ),
            **ERRORS,
        },
        extensions={"x-implementation-status": "implemented", "x-utask-callers": ["integration"]},
    )
    def post(self, request, project_id):
        body = IntegrationAuthorizeInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if request.query_params:
            raise CoreAPIError("VALIDATION_ERROR", "Yêu cầu này không nhận tham số bổ sung.")
        with readable_project(request.user, project_id) as project:
            decision = {"project_id": str(project.pk), "action": "github.read", "allowed": True}
        return success_response(
            decision,
            message="Bạn được phép đọc hoạt động GitHub của dự án.",
        )
