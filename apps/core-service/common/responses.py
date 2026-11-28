"""Shared API response envelope builders."""

from rest_framework.response import Response

from common.serialization import json_value
from common.serializers import ResponseEnvelopeSerializer


def build_envelope(data, message="Thao tác thành công.", *, success=True, meta=None, error=None):
    """Build the unified 5-key API response envelope."""
    return ResponseEnvelopeSerializer(
        {
            "success": success,
            "message": message,
            "data": json_value(data) if success else None,
            "meta": json_value(meta) if (success and meta is not None) else None,
            "error": None if success else (error or {"code": "API_ERROR", "details": []}),
        }
    ).data


def success_response(data, *, status=200, meta=None, message="Thao tác thành công."):
    return Response(build_envelope(data, message, meta=meta), status=status)
