from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services import receipt_scope, require_key
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import KEY_PARAMETER, TASK
from apps.tasks.queries import visible_task
from apps.tasks.serializers import SubtaskSerializer
from apps.tasks.services.hierarchy import create_subtask


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
