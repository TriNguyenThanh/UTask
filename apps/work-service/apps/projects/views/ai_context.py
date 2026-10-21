"""HTTP authorize/context nội bộ cho caller AI."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.projects.queries.ai_context import authorize_target, read_ai_context
from apps.projects.serializers.ai_context import (
    AIAuthorizeInputSerializer,
    AIAuthorizeResultSerializer,
    ContextDocumentSerializer,
    ContextTargetSerializer,
    TargetSerializer,
)
from common.errors import WorkError
from common.internal_api import InternalReadView
from common.responses import success_response
from common.service_permissions import AIServicePermission
from config.api_documentation import ERRORS, envelope_schema

AUTH = [{"WorkBearer": [], "WorkServiceKey": []}]
TARGET_PARAMETERS = [
    OpenApiParameter("target_type", str, OpenApiParameter.PATH, enum=["project", "task", "sprint"]),
    OpenApiParameter("target_id", {"type": "string", "format": "uuid"}, OpenApiParameter.PATH),
]


class AIAuthorizeView(InternalReadView):
    permission_classes = [IsAuthenticated, AIServicePermission]

    @extend_schema(
        operation_id="internal_ai_authorize",
        auth=AUTH,
        parameters=TARGET_PARAMETERS,
        request=AIAuthorizeInputSerializer,
        responses={
            200: envelope_schema("AIAuthorizeEnvelope", AIAuthorizeResultSerializer),
            **ERRORS,
        },
        extensions={"x-implementation-status": "implemented", "x-utask-callers": ["ai"]},
    )
    def post(self, request, target_type, target_id):
        target = TargetSerializer(data={"target_type": target_type, "target_id": target_id})
        target.is_valid(raise_exception=True)
        body = AIAuthorizeInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if request.query_params:
            raise WorkError("VALIDATION_ERROR", "Yêu cầu này không nhận tham số bổ sung.")
        authorize_target(
            request.user, **target.validated_data, intent=body.validated_data["intent"]
        )
        return success_response(
            {**target.data, "action": "ai.analyze", "allowed": True},
            message="Bạn được phép phân tích nội dung đã chọn.",
        )


class AIContextView(InternalReadView):
    permission_classes = [IsAuthenticated, AIServicePermission]

    @extend_schema(
        operation_id="internal_ai_context",
        auth=AUTH,
        parameters=[
            *TARGET_PARAMETERS,
            OpenApiParameter(
                "domain", str, OpenApiParameter.PATH, enum=["project", "task", "team", "progress"]
            ),
        ],
        responses={200: ContextDocumentSerializer, **ERRORS},
        extensions={"x-implementation-status": "implemented", "x-utask-callers": ["ai"]},
    )
    def get(self, request, target_type, target_id, domain):
        target = ContextTargetSerializer(
            data={"target_type": target_type, "target_id": target_id, "domain": domain}
        )
        target.is_valid(raise_exception=True)
        if request.query_params or request.body:
            raise WorkError(
                "VALIDATION_ERROR", "Yêu cầu này không nhận nội dung hoặc tham số bổ sung."
            )
        data = read_ai_context(request.user, **target.validated_data)
        return Response(ContextDocumentSerializer(data).data)
