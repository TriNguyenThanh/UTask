from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services import receipt_scope, require_key
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import KEY_PARAMETER, TASK
from apps.tasks.queries import visible_task
from apps.tasks.serializers import (
    DeletedRelationSerializer,
    RelationInputSerializer,
    RelationSerializer,
    SubtaskSerializer,
)
from apps.tasks.services.hierarchy import create_subtask
from apps.tasks.services.relations import relation_command
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
