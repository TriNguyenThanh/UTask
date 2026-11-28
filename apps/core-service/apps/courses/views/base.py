from drf_spectacular.utils import OpenApiParameter
from rest_framework.views import APIView

from common.parsers import StrictJSONParser

IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=True
)
CURSOR_LIST_PARAMETERS = [
    OpenApiParameter("page_size", int),
    OpenApiParameter("cursor", str),
]


class ClassroomAPIView(APIView):
    """Base APIView enforcing strict JSON-only parsing for Classroom endpoints."""

    parser_classes = [StrictJSONParser]
