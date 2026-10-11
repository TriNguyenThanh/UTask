from collections.abc import Mapping

from rest_framework.renderers import JSONRenderer

from common.responses import build_envelope
from common.serializers import ResponseEnvelopeSerializer

ENVELOPE_FIELDS = frozenset(ResponseEnvelopeSerializer().fields)


class EnvelopeJSONRenderer(JSONRenderer):
    """One envelope for every DRF endpoint; exception headers remain on Response."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        context = renderer_context or {}
        response = context.get("response")
        is_envelope = (
            isinstance(data, Mapping)
            and set(data) == ENVELOPE_FIELDS
            and isinstance(data["success"], bool)
            and isinstance(data["message"], str)
            and (data["error"] is None or isinstance(data["error"], Mapping))
        )
        if not is_envelope:
            ok = response is None or 200 <= response.status_code < 300
            message = (
                str(data.get("detail", "Thao tác thành công."))
                if isinstance(data, Mapping)
                else "Thao tác thành công."
            )
            payload = None if isinstance(data, Mapping) and set(data) == {"detail"} else data
            if message == "Password reset e-mail has been sent.":
                message = (
                    "Nếu tài khoản đủ điều kiện, hướng dẫn đặt lại mật khẩu "
                    "đã được đưa vào hàng đợi."
                )
            view = context.get("view")
            if ok and view is not None:
                messages = getattr(view, "success_messages", {})
                request = context.get("request")
                message = messages.get(getattr(request, "method", ""), message)
                message = getattr(view, "success_message", message)
            data = build_envelope(
                payload, message, success=ok, meta=getattr(response, "identity_meta", None)
            )
        return super().render(data, accepted_media_type, renderer_context)
