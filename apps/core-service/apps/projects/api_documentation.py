"""Ràng buộc OpenAPI của document context và caller nội bộ."""

from drf_spectacular.extensions import OpenApiSerializerExtension


class WorkContextDocumentSchema(OpenApiSerializerExtension):
    """Khai báo trực tiếp schema theo domain, không tạo proxy rồi ghi đè."""

    target_class = "apps.projects.serializers.ai_context.ContextDocumentSerializer"

    def map_serializer(self, auto_schema, direction):
        from apps.projects.serializers import ai_context as serializers

        domain_schemas = {
            domain: auto_schema.resolve_serializer(serializer(), direction).ref
            for domain, serializer in serializers.DATA_SERIALIZERS.items()
        }
        for serializer in (
            *serializers.DATA_SERIALIZERS.values(),
            serializers.TaskSummarySerializer,
            serializers.SprintSummarySerializer,
            serializers.TeamMemberContextSerializer,
            serializers.ProgressMetricSerializer,
        ):
            schema = auto_schema.resolve_serializer(serializer(), direction).schema
            schema["additionalProperties"] = False
            for field in schema["properties"].values():
                if field.get("type") == "array":
                    field["maxItems"] = 100
        schema = auto_schema._map_serializer(self.target, direction, bypass_extensions=True)
        schema["additionalProperties"] = False
        schema["allOf"] = [
            {
                "if": {"properties": {"status": {"enum": ["available", "partial"]}}},
                "then": {
                    "oneOf": [
                        {"properties": {"domain": {"const": domain}, "data": reference}}
                        for domain, reference in domain_schemas.items()
                    ]
                },
            },
            {
                "if": {"properties": {"status": {"const": "partial"}}},
                "then": {
                    "properties": {"warning": {"type": "string", "minLength": 1, "maxLength": 500}}
                },
            },
        ]
        return schema


def document_ai_context(result, generator, request, public):
    """Chỉ bổ sung server/header/mô tả HTTP cho ba route nội bộ."""
    for item in result["paths"].values():
        for method in ("get", "post"):
            operation = item.get(method, {})
            if operation.get("operationId") not in {
                "internal_ai_authorize",
                "internal_ai_context",
                "internal_integration_github_authorize",
            }:
                continue
            operation["servers"] = [{"url": "http://work-service:8000"}]
            operation["responses"]["200"]["headers"] = {
                "Cache-Control": {"schema": {"type": "string", "const": "no-store"}}
            }
            operation["description"] = (
                "Chỉ caller nội bộ đúng endpoint. "
                "Bearer người dùng và X-Service-Key cùng bắt buộc. "
                "Kiểm quyền hiện tại, không ghi dữ liệu nghiệp vụ, không lưu cache. "
                "Context trực tiếp tối đa 65536 byte UTF-8, mỗi mảng tối đa 100 mục; "
                "cắt dữ liệu phải báo partial/warning; số liệu tính trên toàn phạm vi. "
                "Sprint đóng trả stale từ snapshot lịch sử, không dựng lại từ task hiện tại."
            )
    return result
