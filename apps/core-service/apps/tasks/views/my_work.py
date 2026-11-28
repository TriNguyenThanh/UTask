from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.views import ERRORS
from apps.tasks.my_work_queries import read_my_tasks
from apps.tasks.serializers.my_work import (
    DUE_BUCKET_CHOICES,
    ORDERING_CHOICES,
    MyTaskSerializer,
    MyTasksQuerySerializer,
)
from common.responses import success_response
from config.api_documentation import envelope_schema

MY_TASKS_ENVELOPE = envelope_schema("MyTasksEnvelope", MyTaskSerializer, many=True, paginated=True)

MY_TASKS_PARAMETERS = [
    OpenApiParameter("project_id", str, description="Lọc theo UUID dự án."),
    OpenApiParameter(
        "priority", str, enum=["LOW", "MEDIUM", "HIGH", "URGENT"], description="Lọc mức ưu tiên."
    ),
    OpenApiParameter("is_blocked", bool, description="Lọc công việc đang bị chặn."),
    OpenApiParameter(
        "due_bucket",
        str,
        enum=DUE_BUCKET_CHOICES,
        description=(
            "Nhóm hạn theo ngày nghiệp vụ Asia/Ho_Chi_Minh: overdue (< hôm nay), today (hôm nay), "
            "this_week (7 ngày tới tính từ hôm nay), upcoming (sau 7 ngày), no_due (chưa đặt hạn)."
        ),
    ),
    OpenApiParameter(
        "include_completed",
        bool,
        description="Bao gồm công việc ở trạng thái COMPLETED/CANCELLED (mặc định false).",
    ),
    OpenApiParameter("search", str, description="Tìm theo tiêu đề, mô tả hoặc mã công việc."),
    OpenApiParameter(
        "ordering",
        str,
        enum=ORDERING_CHOICES,
        description=(
            "Sắp xếp (mặc định due_date; hỗ trợ due_date, -due_date, priority, updated_at)."
        ),
    ),
    OpenApiParameter("cursor", str, description="Con trỏ phân trang."),
    OpenApiParameter("page_size", int, description="Số bản ghi mỗi trang (1..100, mặc định 20)."),
]


class MyTasksView(GenericAPIView):
    serializer_class = MyTasksQuerySerializer

    @extend_schema(
        operation_id="me_tasks_list",
        description=(
            "Danh sách công việc xuyên dự án được gán cho người dùng hiện tại trên các dự án "
            "đang hoạt động mà người dùng là thành viên đang hoạt động."
        ),
        parameters=MY_TASKS_PARAMETERS,
        responses={200: MY_TASKS_ENVELOPE, **ERRORS},
    )
    def get(self, request):
        serializer = self.get_serializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)
        rows, meta = read_my_tasks(request.user, serializer.validated_data)
        return success_response(
            rows,
            meta=meta,
            message="Đã tải danh sách công việc của bạn.",
        )
