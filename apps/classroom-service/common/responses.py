from rest_framework.response import Response

from common.serialization import json_value
from common.serializers import ResponseEnvelopeSerializer


def build_envelope(data, message="Thao tác thành công.", *, success=True, meta=None, error=None):
    return ResponseEnvelopeSerializer(
        {
            "success": success,
            "message": message,
            "data": json_value(data) if success else None,
            "meta": meta if success else None,
            "error": None if success else error,
        }
    ).data


def success_response(data, *, status=200, meta=None, message="Thao tác thành công."):
    return Response(build_envelope(data, message, meta=meta), status=status)
