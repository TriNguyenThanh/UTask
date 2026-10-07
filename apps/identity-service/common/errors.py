from collections.abc import Sequence
from typing import Any

from rest_framework.exceptions import APIException


class IdentityAPIError(APIException):
    """An API error with the public code/message/details contract."""

    status_code = 400
    default_code = "API_ERROR"

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        self.public_code = code
        self.public_message = message
        self.public_details = list(details or [])
        self.status_code = status_code
        super().__init__(detail=message, code=code)
