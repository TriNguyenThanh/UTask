from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects import queries
from apps.projects.queries.projects import state_list
from apps.projects.serializers.states import (
    CreateStateSerializer,
    DeleteStateSerializer,
    PatchStateSerializer,
    StateSerializer,
)
from apps.projects.services.states import state_command
from common.responses import success_response
from config.api_documentation import ERRORS, envelope_schema

STATES = envelope_schema("StateListEnvelope", StateSerializer, many=True, paginated=True)


class StateListView(GenericAPIView):
    serializer_class = StateSerializer

    @extend_schema(responses={200: STATES, **ERRORS})
    def get(self, request, project_id):
        rows = state_list(request.user, project_id)
        meta = {
            "pagination": {
                "total_count": len(rows),
                "page_size": max(50, len(rows)),
                "next_cursor": None,
                "prev_cursor": None,
                "has_next": False,
            }
        }
        return success_response(
            StateSerializer(rows, many=True).data,
            meta=meta,
            message="Đã lấy danh sách cột trạng thái.",
        )

    @extend_schema(
        request=CreateStateSerializer,
        responses={201: envelope_schema("CreatedStateEnvelope", StateSerializer), **ERRORS},
    )
    def post(self, request, project_id):
        queries.visible_project(request.user, project_id, for_write=True)
        serializer = CreateStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return state_command(request.user, project_id, serializer.validated_data)


STATE = envelope_schema("StateEnvelope", StateSerializer)


DELETED_STATE = envelope_schema("DeletedStateEnvelope", DeleteStateSerializer)


class StateDetailView(GenericAPIView):
    serializer_class = PatchStateSerializer

    @extend_schema(request=PatchStateSerializer, responses={200: STATE, **ERRORS})
    def patch(self, request, project_id, state_id):
        queries.visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return state_command(request.user, project_id, serializer.validated_data, state_id=state_id)
