from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services import receipt_scope, require_key
from apps.projects.queries import visible_project
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import APPLY, KEY_PARAMETER
from apps.tasks.permissions import require_member_fields, require_task_writer
from apps.tasks.queries import ai_operation, visible_task
from apps.tasks.serializers.ai import (
    ActionApplySerializer,
    ApplyResultSerializer,
    BacklogApplySerializer,
    SubtaskApplySerializer,
)
from apps.tasks.services.ai_actions import apply_actions
from apps.tasks.services.ai_apply import apply_tasks
from apps.tasks.services.ai_verification import verified_action_proof, verified_proof
from common.responses import success_response


class BacklogApplyView(GenericAPIView):
    serializer_class = BacklogApplySerializer

    @extend_schema(
        request=BacklogApplySerializer, parameters=[KEY_PARAMETER], responses={201: APPLY, **ERRORS}
    )
    def post(self, request, project_id):
        project = visible_project(request.user, project_id, for_write=True)
        require_task_writer(project, request.user, leader_only=True)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        scope = receipt_scope(request, key)
        proof = verified_proof(request.user, project.pk, payload, scope)
        return apply_tasks(request.user, project.pk, payload, scope, proof)


class SubtaskApplyView(GenericAPIView):
    serializer_class = SubtaskApplySerializer

    @extend_schema(
        request=SubtaskApplySerializer, parameters=[KEY_PARAMETER], responses={201: APPLY, **ERRORS}
    )
    def post(self, request, parent_task_id):
        parent = visible_task(request.user, parent_task_id, for_write=True)
        require_task_writer(parent.project, request.user, parent)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        scope = receipt_scope(request, key)
        member = require_task_writer(parent.project, request.user, parent)
        for item in payload["subtasks"]:
            require_member_fields(
                member,
                item,
                {
                    "local_id",
                    "ai_revision",
                    "dependencies",
                    "title",
                    "description_html",
                    "acceptance_criteria",
                },
            )
        proof = verified_proof(request.user, parent.project_id, payload, scope, parent_id=parent.pk)
        return apply_tasks(
            request.user, parent.project_id, payload, scope, proof, parent_id=parent.pk
        )


class OperationView(GenericAPIView):
    serializer_class = ApplyResultSerializer

    @extend_schema(responses={200: APPLY, **ERRORS})
    def get(self, request, project_id, operation_id):
        visible_project(request.user, project_id)
        receipt = ai_operation(project_id, operation_id)
        return success_response(
            receipt.response_body["data"], message="Đã tải kết quả áp dụng đề xuất."
        )


class ActionApplyView(GenericAPIView):
    serializer_class = ActionApplySerializer

    @extend_schema(
        request=ActionApplySerializer, parameters=[KEY_PARAMETER], responses={200: APPLY, **ERRORS}
    )
    def post(self, request, project_id):
        project = visible_project(request.user, project_id, for_write=True)
        require_task_writer(project, request.user, leader_only=True)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        scope = receipt_scope(request, key)
        proof = verified_action_proof(request.user, project.pk, payload, scope)
        return apply_actions(request.user, project.pk, payload, scope, proof)
