"""DRF JSON parsing with a controlled error for excessive nesting."""

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class WorkJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return super().parse(stream, media_type=media_type, parser_context=parser_context)
        except RecursionError as exc:
            raise ParseError(
                "Dữ liệu gửi lên có cấu trúc lồng nhau vượt quá giới hạn cho phép."
            ) from exc
