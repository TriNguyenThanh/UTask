from __future__ import annotations

import asyncio

from errors import WorkflowTimeoutError
from models import AiResult, CreateAiRequest

from .ports import ModelProvider


class BoundedWorkflow:
    """Giới hạn thời gian gọi provider; ADK workflow sẽ được triển khai sau."""

    def __init__(self, provider: ModelProvider, timeout_seconds: float) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def run(self, request: CreateAiRequest) -> AiResult:
        try:
            return await asyncio.wait_for(
                self._provider.generate(request), timeout=self._timeout_seconds
            )
        except TimeoutError as error:
            raise WorkflowTimeoutError() from error
