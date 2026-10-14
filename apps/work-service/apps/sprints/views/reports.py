from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.sprints.queries.scope import scope_read
from apps.sprints.serializers.reports import BurndownSerializer, ProgressSerializer
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema


class ProgressView(GenericAPIView):
    serializer_class = ProgressSerializer

    @extend_schema(
        responses={200: envelope_schema("SprintProgressEnvelope", ProgressSerializer), **ERRORS}
    )
    def get(self, request, sprint_id):
        return success_response(
            self.get_serializer(scope_read(request.user, sprint_id)).data,
            message="Đã lấy số liệu tiến độ chu kỳ làm việc.",
        )


class BurndownView(GenericAPIView):
    serializer_class = BurndownSerializer

    @extend_schema(
        responses={200: envelope_schema("BurndownEnvelope", BurndownSerializer), **ERRORS}
    )
    def get(self, request, sprint_id):
        return success_response(
            self.get_serializer(scope_read(request.user, sprint_id, burndown=True)).data,
            message="Đã lấy số liệu công việc còn lại theo ngày.",
        )
