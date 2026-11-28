from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.utils import OpenApiParameter

from apps.tasks.serializers.ai import ApplyResultSerializer
from apps.tasks.serializers.tasks import ExpandedTaskSerializer, TaskSerializer
from config.api_documentation import envelope_schema


class TaskProjectionSchema(OpenApiSerializerExtension):
    target_class = "apps.tasks.serializers.tasks.ExpandedTaskSerializer"
    match_subclasses = True

    def map_serializer(self, auto_schema, direction):
        schema = auto_schema._map_serializer(self.target, direction, bypass_extensions=True)
        # Query fields/expand intentionally omit properties; keep readOnly unchanged.
        if direction == "response":
            schema.pop("required", None)
        return schema


TASK = envelope_schema("TaskEnvelope", TaskSerializer)
READ_TASK = envelope_schema("TaskReadEnvelope", ExpandedTaskSerializer)
TASK_LIST = envelope_schema("TaskListEnvelope", ExpandedTaskSerializer, many=True, paginated=True)
KEY_PARAMETER = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
LIST_PARAMETERS = [
    OpenApiParameter(name, str)
    for name in [
        "cursor",
        "fields",
        "expand",
        "status",
        "search",
        "state_id",
        "epic_id",
        "parent_id",
        "type",
        "assignee_id",
        "label_id",
        "priority",
        "is_blocked",
        "due_date_from",
        "due_date_to",
        "sprint_id",
    ]
] + [OpenApiParameter("page_size", int)]


APPLY = envelope_schema("ApplyResultEnvelope", ApplyResultSerializer)
