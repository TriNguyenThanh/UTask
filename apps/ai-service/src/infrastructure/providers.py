"""Adapter mặc định trả lỗi khi chưa cấu hình provider thật."""

from errors import ProviderUnavailableError
from models import AiResult, CreateAiRequest


class UnconfiguredProvider:
    """Fail closed until a real provider adapter is selected and configured."""

    async def generate(self, request: CreateAiRequest) -> AiResult:
        del request
        raise ProviderUnavailableError()
