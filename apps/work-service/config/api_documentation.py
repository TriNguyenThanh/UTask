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
