from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.queries.board import read_board
from apps.projects.serializers.board import (
    BoardColumnPageSerializer,
    BoardFilterSerializer,
    BoardSerializer,
)
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

FILTER_PARAMETERS = [
    OpenApiParameter("sprint_id", str),
    OpenApiParameter("assignee_id", str),
    OpenApiParameter("priority", str),
    OpenApiParameter("is_blocked", bool),
]


class BoardView(GenericAPIView):
    serializer_class = BoardFilterSerializer

    @extend_schema(
        parameters=FILTER_PARAMETERS + [OpenApiParameter("limit_per_column", int)],
        responses={200: envelope_schema("BoardEnvelope", BoardSerializer), **ERRORS},
    )
    def get(self, request, project_id):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return success_response(
            read_board(request.user, project_id, serializer.validated_data),
            message="Đã lấy bảng công việc của dự án.",
        )


class BoardColumnView(GenericAPIView):
    serializer_class = BoardFilterSerializer

    @extend_schema(
        parameters=FILTER_PARAMETERS
        + [OpenApiParameter("page_size", int), OpenApiParameter("cursor", str)],
        responses={
            200: envelope_schema("BoardColumnEnvelope", BoardColumnPageSerializer),
            **ERRORS,
        },
    )
    def get(self, request, project_id, state_id):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return success_response(
            read_board(request.user, project_id, serializer.validated_data, state_id=state_id),
            message="Đã lấy danh sách công việc trong cột trạng thái.",
        )
