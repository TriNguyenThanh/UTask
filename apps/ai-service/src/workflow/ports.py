"""Hợp đồng gọi mô hình mà bounded workflow sử dụng."""

from typing import Protocol

from models import AiResult, CreateAiRequest


class ModelProvider(Protocol):
    async def generate(self, request: CreateAiRequest) -> AiResult:
        """Generate a typed proposal for one phase-1 intent."""
