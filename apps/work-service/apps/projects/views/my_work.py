from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.queries.my_work import read_my_overview
from apps.projects.serializers.my_work import MyOverviewSerializer
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

MY_OVERVIEW_ENVELOPE = envelope_schema("MyOverviewEnvelope", MyOverviewSerializer)


class MyOverviewView(GenericAPIView):
    serializer_class = MyOverviewSerializer

    @extend_schema(
        operation_id="me_overview_retrieve",
        description=(
            "Tổng hợp cá nhân xuyên dự án cho màn hình Công việc của tôi: bộ đếm công việc "
            "đang mở, danh sách dự án đang tham gia kèm chu kỳ hiện tại và tiến độ "
            "work-metrics-v1, cùng tối đa 20 công việc sắp tới hạn."
        ),
        responses={200: MY_OVERVIEW_ENVELOPE, **ERRORS},
    )
    def get(self, request):
        return success_response(
            read_my_overview(request.user),
            message="Đã tải tổng quan công việc cá nhân.",
        )
