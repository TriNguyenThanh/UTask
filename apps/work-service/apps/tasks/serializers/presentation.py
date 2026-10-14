from apps.tasks import queries
from apps.tasks.serializers.tasks import ExpandedTaskSerializer, TaskSerializer
from common.errors import WorkError


def validate_task_projection(*, fields=None, expand=None, many=True):
    field_names = set(fields.split(",")) if fields else None
    expansions = set(expand.split(",")) if expand else set()
    if field_names and not field_names <= set(TaskSerializer.Meta.fields):
        raise WorkError("VALIDATION_ERROR", "Tham số fields chứa trường dữ liệu không được hỗ trợ.")
    if not expansions <= {
        "state",
        "epic",
        "labels",
        "assignees",
        "relations",
        "subtasks",
        "attachments",
        "github_links",
    }:
        raise WorkError(
            "VALIDATION_ERROR", "Tham số expand chứa đối tượng liên kết không được hỗ trợ."
        )
    heavy = expansions & {"relations", "subtasks", "attachments", "github_links"}
    if many and heavy:
        raise WorkError(
            "VALIDATION_ERROR",
            "Các quan hệ dữ liệu mở rộng chỉ được hỗ trợ xem ở trang chi tiết công việc.",
        )
    return field_names, expansions


def serialize_tasks(rows, *, fields=None, expand=None, many=True):
    field_names, expansions = validate_task_projection(fields=fields, expand=expand, many=many)
    heavy = expansions & {"relations", "subtasks", "attachments", "github_links"}
    detail = queries.detail_expansions(rows, heavy) if heavy else {}
    instances = list(rows) if many else [rows]
    profiles = {}
    if "assignees" in expansions:
        ids = {a.user_id for row in instances for a in row.assignments.all()}
        profiles = queries.user_profiles(ids)
    serializer = ExpandedTaskSerializer(
        instances if many else rows, many=many, context={"profiles": profiles, "detail": detail}
    )
    target = serializer.child if many else serializer
    for name in {
        "state",
        "epic",
        "labels",
        "assignees",
        "relations",
        "subtasks",
        "attachments",
        "github_links",
    } - expansions:
        target.fields.pop(name)
    if field_names:
        for name in set(TaskSerializer.Meta.fields) - field_names:
            target.fields.pop(name)
    return serializer.data
