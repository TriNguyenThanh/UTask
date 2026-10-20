from collections.abc import Mapping

from rest_framework.renderers import JSONRenderer

from common.responses import build_envelope
from common.serializers import ResponseEnvelopeSerializer

ENVELOPE_FIELDS = frozenset(ResponseEnvelopeSerializer().fields)

LIBRARY_RESPONSE_MESSAGES = {
    "Password reset e-mail has been sent.": (
        "Nếu tài khoản đủ điều kiện, hướng dẫn đặt lại mật khẩu đã được đưa vào hàng đợi."
    ),
    "Password has been reset with the new password.": "Đặt lại mật khẩu thành công.",
    "New password has been saved.": "Đổi mật khẩu thành công. Vui lòng đăng nhập lại.",
    "Successfully logged out.": "Đăng xuất thành công.",
    "Verification e-mail sent.": "Hướng dẫn xác minh email đã được đưa vào hàng đợi.",
    "ok": "Thao tác thành công.",
    "An error has occurred.": "Không thể hoàn tất yêu cầu.",
    "Refresh token was not included in cookie data.": "Thiếu thông tin phiên đăng nhập.",
    "Refresh token was not included in request data.": "Thiếu thông tin phiên đăng nhập.",
}


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
            message = LIBRARY_RESPONSE_MESSAGES.get(message, message)
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
