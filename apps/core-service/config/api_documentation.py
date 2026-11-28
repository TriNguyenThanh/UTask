"""Unified OpenAPI 3.1.0 schema extensions and envelope helpers for UTask Core Service."""

from copy import deepcopy

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter, extend_schema_field, inline_serializer
from rest_framework import serializers

from common.serializers import APIErrorSerializer, ListMetaSerializer, ResponseEnvelopeSerializer


class CoreJWTScheme(SimpleJWTScheme):
    target_class = "common.authentication.CoreJWTAuthentication"
    name = "jwtAuth"


class IdentityDetailResponseSchema(OpenApiSerializerExtension):
    target_class = "drf_spectacular.contrib.rest_auth.RestAuthDetailSerializer"
    priority = 1

    def map_serializer(self, auto_schema, direction):
        return {"type": "null"}


class CoreAutoSchema(AutoSchema):
    """Auto-wrap Identity/library responses without double-wrapping enveloped endpoints."""

    def _is_already_enveloped(self, schema: dict) -> bool:
        if not isinstance(schema, dict):
            return False
        ref = schema.get("$ref", "")
        if "Envelope" in ref or ref.endswith("/ResponseEnvelope"):
            return True
        props = schema.get("properties")
        return isinstance(props, dict) and {"success", "message", "data", "meta", "error"} <= set(
            props
        )

    def _is_raw_endpoint(self) -> bool:
        return (
            self.path.endswith("/.well-known/jwks.json")
            or self.path.endswith("/healthz")
            or "/api/v1/internal/ai/targets/" in self.path
            and "/contexts/" in self.path
            or self.path.endswith("/api/v1/internal/users/notification-contacts")
            or self.path.endswith("/api/v1/internal/notifications/resolve")
        )

    def _get_response_bodies(self, direction="response"):
        responses = super()._get_response_bodies(direction)
        if direction != "response" or self._is_raw_endpoint():
            return responses
        envelope = self.resolve_serializer(ResponseEnvelopeSerializer(), "response")
        for code, response in responses.items():
            if not code.startswith("2"):
                continue
            content = response.setdefault("content", {}).setdefault("application/json", {})
            existing = content.get("schema", {"type": "null"})
            if self._is_already_enveloped(existing):
                continue
            schema = deepcopy(envelope.schema)
            schema["properties"]["data"] = existing
            content["schema"] = schema
        view_module = getattr(getattr(self.view, "__class__", None), "__module__", "")
        is_identity_view = (
            self.path.startswith("/api/auth/")
            or self.path.startswith("/api/v1/internal/auth/")
            or view_module.startswith(("apps.accounts.", "apps.authentication.", "dj_rest_auth."))
        )
        if is_identity_view:
            for code in (400, 401, 403, 404, 405, 422, 429, 500, 503):
                responses.setdefault(
                    str(code),
                    {
                        "description": "Core API error",
                        "content": {"application/json": {"schema": envelope.ref}},
                    },
                )
        return responses


class RoleChangeAutoSchema(CoreAutoSchema):
    """Include request body documentation for DELETE role revocation endpoint."""

    def _get_request_body(self, direction="request"):
        if self.method != "DELETE":
            return super()._get_request_body(direction)
        schema, required = self._get_request_for_media_type(
            self.get_request_serializer(), direction
        )
        return {"content": {"application/json": {"schema": schema}}, "required": required}


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
    name="CoreErrorEnvelope",
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
STATUS_PARAMETER = OpenApiParameter("status", str)


def document_connection_receipt(result, generator, request, public):
    """Preserve wire constraints for internal GitHub operation receipt in OpenAPI."""
    path = result["paths"].get(
        "/api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}"
    )
    if path is None:
        return result
    schemas = result["components"]["schemas"]
    if "WorkGitHubOperationReceipt" not in schemas:
        return result
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
    return result
