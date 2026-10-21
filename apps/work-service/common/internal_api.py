"""Biên HTTP JSON không lưu cache cho API đọc nội bộ."""

from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView


class InternalJSONRenderer(JSONRenderer):
    def get_indent(self, accepted_media_type, renderer_context):
        # Wire size must stay bounded even when Accept requests pretty JSON.
        return None


class InternalReadView(APIView):
    renderer_classes = [InternalJSONRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response
