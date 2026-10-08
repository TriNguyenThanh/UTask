"""ADK workflow điều phối agent, validation và retry/revise trong budget chung."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from random import uniform

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import errors, types
from pydantic import ValidationError

from errors import ServiceError, failure
from models import Intent
from models.validation import validate_result


class ProposalWorkflow(BaseAgent):
    intent: Intent
    revisions: int = 1
    validate_context: Callable[[], None]

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        agent = self.sub_agents[0]
        for attempt in range(self.revisions + 1):
            raw = ""
            try:
                async for event in agent.run_async(ctx):
                    if event.is_final_response() and event.content:
                        raw = "".join(part.text or "" for part in event.content.parts or [])
                    yield event
            except ServiceError:
                raise
            except errors.APIError as error:
                retryable = error.code in {429, 500, 502, 503, 504}
                if retryable and attempt < self.revisions:
                    await asyncio.sleep(0.1 * 2**attempt + uniform(0, 0.05))
                    continue
                raise failure("PROVIDER_UNAVAILABLE", 502, retryable=retryable) from error
            except Exception as error:
                raise failure("PROVIDER_UNAVAILABLE", 502) from error
            try:
                result = validate_result(self.intent, raw)
            except (ValidationError, ValueError):
                if attempt == self.revisions:
                    raise failure("OUTPUT_VALIDATION_FAILED", 422) from None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=(
                                    "Output chưa đúng schema của intent. "
                                    "Hãy trả lại duy nhất JSON hợp lệ."
                                )
                            )
                        ],
                    ),
                )
                continue
            self.validate_context()
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={"validated_proposal": result.model_dump(mode="json")}
                ),
            )
            return
        raise failure("OUTPUT_VALIDATION_FAILED", 422)


def build_workflow(
    intent: Intent, agent: LlmAgent, revisions: int, validate_context: Callable[[], None]
) -> ProposalWorkflow:
    return ProposalWorkflow(
        name="proposal_workflow",
        intent=intent,
        revisions=revisions,
        sub_agents=[agent],
        validate_context=validate_context,
    )
