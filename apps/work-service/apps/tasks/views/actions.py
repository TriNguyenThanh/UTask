from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services import receipt_scope, require_key
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import KEY_PARAMETER, TASK
from apps.tasks.queries import visible_task
from apps.tasks.serializers import (
    BlockSerializer,
    DeletedRelationSerializer,
    RelationInputSerializer,
    RelationSerializer,
    SubtaskSerializer,
    TaskVersionSerializer,
    TransitionSerializer,
    WorkflowTaskSerializer,
)
from apps.tasks.services.hierarchy import create_subtask
from apps.tasks.services.relations import relation_command
from apps.tasks.services.workflow import block_task, transition_task
from config.api_documentation import envelope_schema


class SubtaskView(GenericAPIView):
    serializer_class = SubtaskSerializer

    @extend_schema(
        request=SubtaskSerializer, parameters=[KEY_PARAMETER], responses={201: TASK, **ERRORS}
    )
    def post(self, request, parent_task_id):
        visible_task(request.user, parent_task_id, for_write=True)
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_subtask(
            request.user, parent_task_id, serializer.validated_data, receipt_scope(request, key)
        )


class TransitionView(GenericAPIView):
    serializer_class = TransitionSerializer

    @extend_schema(
        request=TransitionSerializer,
        responses={200: envelope_schema("TransitionEnvelope", WorkflowTaskSerializer), **ERRORS},
    )
    def patch(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return transition_task(request.user, task_id, serializer.validated_data)


class BlockView(GenericAPIView):
    serializer_class = BlockSerializer
    blocked = True

    @extend_schema(request=BlockSerializer, responses={200: TASK, **ERRORS})
    def patch(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return block_task(request.user, task_id, serializer.validated_data, blocked=self.blocked)


class UnblockView(BlockView):
    serializer_class = TaskVersionSerializer
    blocked = False

    @extend_schema(request=TaskVersionSerializer, responses={200: TASK, **ERRORS})
    def patch(self, request, task_id):
        return super().patch(request, task_id)


class RelationView(GenericAPIView):
    serializer_class = RelationInputSerializer

    @extend_schema(
        request=RelationInputSerializer,
        responses={201: envelope_schema("RelationEnvelope", RelationSerializer), **ERRORS},
    )
    def post(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return relation_command(request.user, task_id, serializer.validated_data)


class RelationDetailView(GenericAPIView):
    serializer_class = DeletedRelationSerializer

    @extend_schema(
        request=None,
        responses={
            200: envelope_schema("DeletedRelationEnvelope", DeletedRelationSerializer),
            **ERRORS,
        },
    )
    def delete(self, request, task_id, relation_id):
        visible_task(request.user, task_id, for_write=True)
        return relation_command(request.user, task_id, relation_id=relation_id)
