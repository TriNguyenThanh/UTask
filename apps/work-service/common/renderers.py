from collections.abc import Mapping

from rest_framework.renderers import JSONRenderer

from common.responses import build_envelope


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        is_envelope = (
            isinstance(data, Mapping)
            and set(data) == {"success", "message", "data", "meta", "error"}
            and isinstance(data["success"], bool)
        )
        if not is_envelope:
            response = (renderer_context or {}).get("response")
            ok = response is None or 200 <= response.status_code < 300
            data = build_envelope(
                data, success=ok, error=None if ok else {"code": "API_ERROR", "details": []}
            )
        return super().render(data, accepted_media_type, renderer_context)
