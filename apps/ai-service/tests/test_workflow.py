import asyncio

import pytest

from errors import ProviderUnavailableError, WorkflowTimeoutError
from infrastructure.providers import UnconfiguredProvider
from models import (
    BacklogGenerationRequest,
    BacklogInput,
    BacklogResult,
    CreateAiRequest,
)
from workflow import BoundedWorkflow


class SlowProvider:
    async def generate(self, request: CreateAiRequest) -> BacklogResult:
        del request
        await asyncio.sleep(0.02)
        return BacklogResult(items=[], warnings=[])


@pytest.mark.asyncio
async def test_workflow_converts_provider_timeout_to_stable_error() -> None:
    workflow = BoundedWorkflow(SlowProvider(), timeout_seconds=0.001)
    request = BacklogGenerationRequest(
        intent="backlog_generation",
        input=BacklogInput(description="Test"),
    )

    with pytest.raises(WorkflowTimeoutError) as error:
        await workflow.run(request)

    assert error.value.code == "WORKFLOW_TIMEOUT"


@pytest.mark.asyncio
async def test_workflow_returns_provider_result() -> None:
    workflow = BoundedWorkflow(SlowProvider(), timeout_seconds=1)
    request = BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description="Test")
    )

    result = await workflow.run(request)

    assert result == BacklogResult(items=[], warnings=[])


@pytest.mark.asyncio
async def test_workflow_preserves_provider_error() -> None:
    workflow = BoundedWorkflow(UnconfiguredProvider(), timeout_seconds=1)
    request = BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description="Test")
    )

    with pytest.raises(ProviderUnavailableError) as caught:
        await workflow.run(request)

    assert caught.value.status_code == 502
    assert caught.value.retryable is True
