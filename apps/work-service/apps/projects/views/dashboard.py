from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.queries.dashboard import read_dashboard
from apps.projects.serializers.dashboard import DashboardSerializer
from common.errors import WorkError
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema


class DashboardView(GenericAPIView):
    serializer_class = DashboardSerializer

    @extend_schema(
        responses={200: envelope_schema("DashboardEnvelope", DashboardSerializer), **ERRORS}
    )
    def get(self, request, project_id):
        if request.query_params:
            raise WorkError(
                "VALIDATION_ERROR",
                "Bảng thông tin tổng quan hiện chưa hỗ trợ bộ lọc tùy chỉnh này.",
            )
        data = read_dashboard(request.user, project_id)
        return success_response(
            self.get_serializer(data).data, message="Đã lấy số liệu công việc của dự án."
        )
