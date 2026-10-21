from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiParameter, extend_schema_field, inline_serializer
from rest_framework import serializers

from common.serializers import APIErrorSerializer, ListMetaSerializer


class WorkBearerScheme(OpenApiAuthenticationExtension):
    target_class = "common.authentication.WorkJWTAuthentication"
    name = "WorkBearer"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


def envelope_schema(name, data_serializer, *, many=False, paginated=False):
    return inline_serializer(
        name=name,
        fields={
            "success": serializers.BooleanField(),
            "message": serializers.CharField(),
            "data": data_serializer(many=many, allow_null=True),
            "meta": ListMetaSerializer(allow_null=True)
            if paginated
            else serializers.DictField(allow_null=True),
            "error": APIErrorSerializer(allow_null=True),
        },
    )


@extend_schema_field({"type": "null"})
class NullErrorDataField(serializers.Field):
    def to_representation(self, value):
        return None


ERROR_RESPONSE = inline_serializer(
    name="WorkErrorEnvelope",
    fields={
        "success": serializers.BooleanField(),
        "message": serializers.CharField(),
        "data": NullErrorDataField(read_only=True),
        "meta": serializers.DictField(allow_null=True),
        "error": APIErrorSerializer(),
    },
)


ERRORS = {
    400: ERROR_RESPONSE,
    401: ERROR_RESPONSE,
    403: ERROR_RESPONSE,
    404: ERROR_RESPONSE,
    409: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
    503: ERROR_RESPONSE,
    500: ERROR_RESPONSE,
}


LIST_PARAMETERS = [
    OpenApiParameter("page_size", int),
    OpenApiParameter("cursor", str),
    OpenApiParameter("status", str),
]


def document_connection_receipt(result, generator, request, public):
    """Giữ ràng buộc wire của biên nhận nội bộ khi xuất OpenAPI từ serializer."""
    path = result["paths"].get(
        "/api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}"
    )
    if path is None:
        return result
    schemas = result["components"]["schemas"]
    receipt = schemas["WorkGitHubOperationReceipt"]
    receipt["additionalProperties"] = False
    fields = receipt["properties"]
    fields["applied"]["const"] = True
    fields["project_id"]["not"] = {"const": "00000000-0000-0000-0000-000000000000"}
    fields["operation_id"].update(
        minLength=1,
        maxLength=100,
        **{"not": {"anyOf": [{"enum": [".", ".."]}, {"pattern": r"[\u0000-\u001f]"}]}},
    )
    fields["status"] = {"type": "string", "const": "PENDING"}
    fields["repo_id"].update(
        minLength=1,
        maxLength=100,
        pattern=r"^[1-9][0-9]{0,99}$",
        **{"not": {"type": "string", "pattern": "[^0-9]"}},
    )
    for field in ("generation", "source_version"):
        fields[field]["description"] = (
            "Wire dùng token JSON integer không phần thập phân hoặc exponent "
            "(1, không phải 1.0/1e0); consumer không ép float sang int."
        )
    envelope = schemas["WorkGitHubOperationReceiptEnvelope"]
    envelope["properties"]["success"]["const"] = True
    envelope["properties"]["data"] = {"$ref": "#/components/schemas/WorkGitHubOperationReceipt"}
    operation = path["get"]
    operation["servers"] = [{"url": "http://work-service:8000"}]
    for parameter in operation["parameters"]:
        parameter["schema"] = {
            "$ref": "#/components/schemas/WorkGitHubOperationReceipt/properties/"
            + parameter["name"]
        }
    content = operation["responses"]["200"]["content"]["application/json"]
    content["examples"] = {
        action: {
            "value": {
                "success": True,
                "message": "Đã lấy kết quả ghi nhận yêu cầu kết nối.",
                "data": {
                    "applied": True,
                    "project_id": "11111111-1111-4111-8111-111111111111",
                    "operation_id": operation_id,
                    "generation": generation,
                    "status": "PENDING",
                    "repo_id": repo_id,
                    "source_version": source_version,
                },
                "meta": None,
                "error": None,
            }
        }
        for action, operation_id, generation, repo_id, source_version in (
            ("connect", "connect:project:1", 1, "12345", 2),
            ("disconnect", "disconnect:project:2", 2, None, 4),
        )
    }
    return result
