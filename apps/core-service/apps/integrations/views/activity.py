from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.integrations.serializers.activity import ProjectGitHubActivitySerializer
from apps.integrations.services.activity import project_github_activity
from common.authentication import bearer_token
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

PROJECT_GITHUB_ACTIVITY = envelope_schema(
    "ProjectGitHubActivityEnvelope", ProjectGitHubActivitySerializer
)


class ProjectGitHubActivityView(APIView):
    @extend_schema(
        operation_id="projects_github_activity_retrieve",
        description=(
            "Lấy hoạt động GitHub gần nhất (nhánh, commit, Pull Request, issue) của kho mã nguồn "
            "đang kết nối với dự án kèm danh sách linked_task_ids đã xác nhận. Khả dụng cho thành "
            "viên đang hoạt động của dự án và giảng viên phụ trách lớp; trả ngay trạng thái "
            "DISCONNECTED/PENDING nếu dự án chưa hoàn tất kết nối."
        ),
        responses={200: PROJECT_GITHUB_ACTIVITY, **ERRORS, 429: ERRORS[400]},
    )
    def get(self, request, project_id):
        data = project_github_activity(request.user, project_id, bearer_token(request))
        return success_response(data, message="Đã lấy thông tin hoạt động GitHub của dự án.")
