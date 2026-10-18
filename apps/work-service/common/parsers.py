"""DRF JSON parsing with a controlled error for excessive nesting."""

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser

from common.json_validation import has_excessive_json_nesting


class WorkJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            data = super().parse(stream, media_type=media_type, parser_context=parser_context)
        except RecursionError as exc:
            raise ParseError(
                "Dữ liệu gửi lên có cấu trúc lồng nhau vượt quá giới hạn cho phép."
            ) from exc
        if has_excessive_json_nesting(data):
            raise ParseError("Dữ liệu gửi lên có cấu trúc lồng nhau vượt quá giới hạn cho phép.")
        return data
