from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services import receipt_scope, require_key
from apps.projects.queries import visible_project
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import KEY_PARAMETER, LIST_PARAMETERS, READ_TASK, TASK, TASK_LIST
from apps.tasks.filters import TaskFilter
from apps.tasks.queries import project_tasks, visible_task
from apps.tasks.serializers import (
    CreateTaskSerializer,
    PatchTaskSerializer,
    TaskVersionSerializer,
)
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.creation import create_task
from apps.tasks.services.mutations import lifecycle_task, update_task
from common.errors import WorkError
from common.pagination import paginate
from common.responses import success_response


class TaskListCreateView(GenericAPIView):
    serializer_class = CreateTaskSerializer

    @extend_schema(parameters=LIST_PARAMETERS, responses={200: TASK_LIST, **ERRORS})
    def get(self, request, project_id):
        params = request.query_params
        allowed = set(TaskFilter.base_filters) | {
            "fields",
            "expand",
            "cursor",
            "page_size",
            "status",
        }
        if set(params) - allowed:
            raise WorkError("VALIDATION_ERROR", "Tham số truy vấn không được hỗ trợ.")
        queryset = project_tasks(
            request.user,
            project_id,
            status=params.get("status", "active"),
            fields=params.get("fields"),
            expand=params.get("expand"),
        )
        filters = TaskFilter(params, queryset=queryset)
        if not filters.is_valid():
            raise WorkError(
                "VALIDATION_ERROR",
                "Bộ lọc công việc không hợp lệ.",
                details=[
                    {"field": key, "issue": issue}
                    for key, errors in filters.errors.as_data().items()
                    for error in errors
                    for issue in error.messages
                ],
            )
        pagination_params = params.copy()
        pagination_params.setdefault("page_size", "50")
        rows, meta = paginate(
            filters.qs,
            pagination_params,
            scope={
                "project": str(project_id),
                "actor": str(request.user.id),
                "filters": {
                    key: params[key]
                    for key in params
                    if key not in {"cursor", "page_size", "fields", "expand"}
                },
            },
        )
        return success_response(
            serialize_tasks(rows, fields=params.get("fields"), expand=params.get("expand")),
            meta=meta,
            message="Đã tải danh sách công việc.",
        )

    @extend_schema(
        request=CreateTaskSerializer, parameters=[KEY_PARAMETER], responses={201: TASK, **ERRORS}
    )
    def post(self, request, project_id):
        visible_project(request.user, project_id, for_write=True)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_task(
            request.user, project_id, serializer.validated_data, receipt_scope(request, key)
        )


class TaskDetailView(GenericAPIView):
    serializer_class = PatchTaskSerializer

    @extend_schema(
        parameters=[OpenApiParameter("expand", str), OpenApiParameter("fields", str)],
        responses={200: READ_TASK, **ERRORS},
    )
    def get(self, request, task_id):
        task = visible_task(request.user, task_id)
        return success_response(
            serialize_tasks(
                task,
                many=False,
                fields=request.query_params.get("fields"),
                expand=request.query_params.get("expand"),
            ),
            message="Đã tải chi tiết công việc.",
        )

    @extend_schema(request=PatchTaskSerializer, responses={200: TASK, **ERRORS})
    def patch(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return update_task(request.user, task_id, serializer.validated_data)

    @extend_schema(request=TaskVersionSerializer, responses={200: TASK, **ERRORS})
    def delete(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = TaskVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return lifecycle_task(
            request.user, task_id, serializer.validated_data["expected_version"], "delete"
        )


class TaskLifecycleView(GenericAPIView):
    serializer_class = TaskVersionSerializer
    action = "archive"

    @extend_schema(request=TaskVersionSerializer, responses={200: TASK, **ERRORS})
    def post(self, request, task_id):
        visible_task(request.user, task_id, for_write=True, deleted=self.action == "restore")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return lifecycle_task(
            request.user, task_id, serializer.validated_data["expected_version"], self.action
        )
