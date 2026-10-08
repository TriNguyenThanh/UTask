"""Build the shared API response body without loading DRF views/renderers."""

from common.serializers import ResponseEnvelopeSerializer


def build_envelope(data, message="Thao tác thành công.", *, success=True, meta=None, error=None):
    """Shared body for rendered responses, errors and durable provisioning receipts."""
    return ResponseEnvelopeSerializer(
        {
            "success": success,
            "message": message,
            "data": data if success else None,
            "meta": meta if success else None,
            "error": None if success else (error or {"code": "API_ERROR", "details": []}),
        }
    ).data
