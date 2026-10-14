from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services.receipts import receipt_scope, require_key
from apps.projects.queries.projects import visible_project
from apps.sprints.queries.scope import sprint_list, visible_sprint
from apps.sprints.serializers.lifecycle import (
    CreateSprintSerializer,
    PatchSprintSerializer,
    ScopeResultSerializer,
    ScopeSerializer,
    SprintSerializer,
    StartSprintSerializer,
)
from apps.sprints.services.lifecycle import create_sprint, start_sprint, update_sprint
from apps.sprints.services.scope import change_scope
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, envelope_schema

SPRINT = envelope_schema("SprintEnvelope", SprintSerializer)


KEY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)


class SprintListCreateView(GenericAPIView):
    serializer_class = CreateSprintSerializer

    @extend_schema(
        parameters=LIST_PARAMETERS,
        responses={
            200: envelope_schema("SprintListEnvelope", SprintSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, request, project_id):
        items, meta = sprint_list(request.user, project_id, request.query_params)
        return success_response(
            SprintSerializer(items, many=True).data,
            meta=meta,
            message="Đã lấy danh sách chu kỳ làm việc.",
        )

    @extend_schema(request=CreateSprintSerializer, responses={201: SPRINT, **ERRORS})
    def post(self, request, project_id):
        visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_sprint(request.user, project_id, serializer.validated_data)


class SprintDetailView(GenericAPIView):
    serializer_class = PatchSprintSerializer

    @extend_schema(responses={200: SPRINT, **ERRORS})
    def get(self, request, sprint_id):
        return success_response(
            SprintSerializer(visible_sprint(request.user, sprint_id)).data,
            message="Đã lấy thông tin chu kỳ làm việc.",
        )

    @extend_schema(request=PatchSprintSerializer, responses={200: SPRINT, **ERRORS})
    def patch(self, request, sprint_id):
        visible_sprint(request.user, sprint_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return update_sprint(request.user, sprint_id, serializer.validated_data)


class SprintStartView(GenericAPIView):
    serializer_class = StartSprintSerializer

    @extend_schema(
        request=StartSprintSerializer, parameters=[KEY], responses={200: SPRINT, **ERRORS}
    )
    def post(self, request, project_id, sprint_id):
        from rest_framework.exceptions import NotFound

        sprint = visible_sprint(request.user, sprint_id, for_write=True)
        if sprint.project_id != project_id:
            raise NotFound("Không tìm thấy chu kỳ làm việc yêu cầu.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return start_sprint(
            request.user,
            sprint_id,
            serializer.validated_data,
            receipt_scope(request, require_key(request)),
        )


class SprintScopeView(GenericAPIView):
    serializer_class = ScopeSerializer

    @extend_schema(
        request=ScopeSerializer,
        parameters=[KEY],
        responses={200: envelope_schema("SprintScopeEnvelope", ScopeResultSerializer), **ERRORS},
    )
    def post(self, request, sprint_id):
        visible_sprint(request.user, sprint_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return change_scope(
            request.user,
            sprint_id,
            serializer.validated_data,
            receipt_scope(request, require_key(request)),
        )
