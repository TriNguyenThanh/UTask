from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.integrations.serializers.repositories import ConnectionReceiptSerializer
from apps.integrations.services.operations import operation_receipt
from common.errors import WorkError
from common.responses import success_response
from common.service_permissions import service_key_allowed
from config.api_documentation import ERRORS, envelope_schema


class IntegrationServicePermission(BasePermission):
    message = "Bạn không có quyền truy cập dữ liệu yêu cầu."

    def has_permission(self, request, view):
        return service_key_allowed(request, "integration")


class ConnectionReceiptView(APIView):
    authentication_classes = []
    permission_classes = [IntegrationServicePermission]

    @extend_schema(
        operation_id="internal_integration_github_receipt",
        description=(
            "Chỉ Integration đọc biên nhận đã commit bằng khóa dịch vụ, không dùng Bearer. "
            "Không nhận query/body. Biên nhận bất biến giữ fact prepare: status luôn PENDING, "
            "kể cả khi kết nối đã hoàn tất; repo_id là null khi ngắt kết nối. "
            "Hai ID phải khớp path sau giải mã; operation_id được percent-encode. "
            "JSON UTF-8 tối đa 65536 byte."
        ),
        parameters=[
            OpenApiParameter(
                "Cache-Control",
                {"type": "string", "const": "no-store"},
                OpenApiParameter.HEADER,
                required=True,
                response=[200],
            ),
        ],
        responses={
            200: envelope_schema("WorkGitHubOperationReceiptEnvelope", ConnectionReceiptSerializer),
            **{status: ERRORS[status] for status in (400, 403, 404, 500, 503)},
        },
        auth=[{"WorkServiceKey": []}],
        extensions={"x-implementation-status": "implemented", "x-utask-callers": ["integration"]},
    )
    def get(self, request, project_id, operation_id):
        if request.query_params or request.body:
            raise WorkError(
                "VALIDATION_ERROR", "Yêu cầu này không nhận nội dung hoặc tham số bổ sung.", 400
            )
        response = success_response(
            operation_receipt(project_id, operation_id),
            message="Đã lấy kết quả ghi nhận yêu cầu kết nối.",
        )
        response["Cache-Control"] = "no-store"
        return response
