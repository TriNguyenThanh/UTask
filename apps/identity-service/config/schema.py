"""drf-spectacular integration. Routes and business serializers remain in their apps."""

from copy import deepcopy

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.openapi import AutoSchema

from common.serializers import ResponseEnvelopeSerializer


class IdentityDetailResponseSchema(OpenApiSerializerExtension):
    """Library detail-only responses become message/data=null in the common renderer.

    The built-in view extension describes data.detail; its serializer extension must
    reflect EnvelopeJSONRenderer, which moves detail into the common message field.
    """

    target_class = "drf_spectacular.contrib.rest_auth.RestAuthDetailSerializer"
    priority = 1

    def map_serializer(self, auto_schema, direction):
        return {"nullable": True, "enum": [None]}


class IdentityJWTScheme(SimpleJWTScheme):
    target_class = "authentication.adapters.access_token_authentication.IdentityJWTAuthentication"


class IdentityAutoSchema(AutoSchema):
    """Reuse the runtime envelope; library introspection supplies each endpoint's data."""

    def _get_response_bodies(self, direction="response"):
        responses = super()._get_response_bodies(direction)
        if direction != "response" or self.path.endswith("/.well-known/jwks.json"):
            return responses
        envelope = self.resolve_serializer(ResponseEnvelopeSerializer(), "response")
        for code, response in responses.items():
            if not code.startswith("2"):
                continue
            content = response.setdefault("content", {}).setdefault("application/json", {})
            schema = deepcopy(envelope.schema)
            schema["properties"]["data"] = content.get("schema", {"nullable": True})
            content["schema"] = schema
        for code in (400, 401, 403, 404, 405, 422, 429, 500, 503):
            responses.setdefault(
                str(code),
                {
                    "description": "Identity API error",
                    "content": {"application/json": {"schema": envelope.ref}},
                },
            )
        return responses
