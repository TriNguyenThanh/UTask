"""ADK workflow điều phối agent, validation và retry/revise trong budget chung."""

import asyncio
import re
from collections.abc import AsyncGenerator, Callable
from random import uniform

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import errors, types
from openai import APIError, APITimeoutError
from pydantic import ValidationError

from errors import ServiceError, failure
from models import Intent
from models.results import AiResult
from models.validation import validate_result


class ProposalWorkflow(BaseAgent):
    intent: Intent
    revisions: int = 1
    validate_context: Callable[[], None]
    finalize_result: Callable[[AiResult], AiResult] | None = None

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        agent = self.sub_agents[0]
        for attempt in range(self.revisions + 1):
            raw = ""
            try:
                async for event in agent.run_async(ctx):
                    if event.is_final_response() and event.content:
                        raw = "".join(
                            part.text or ""
                            for part in event.content.parts or []
                            if not part.thought
                        )
                    yield event
            except ServiceError:
                raise
            except (errors.APIError, APIError) as error:
                status = (
                    error.code
                    if isinstance(error, errors.APIError)
                    else getattr(error, "status_code", None)
                )
                retryable = (
                    status in {429, 500, 502, 503, 504}
                    or isinstance(error, APITimeoutError)
                    or (isinstance(error, APIError) and status is None)
                )
                if retryable and attempt < self.revisions:
                    await asyncio.sleep(0.1 * 2**attempt + uniform(0, 0.05))
                    continue
                raise failure("PROVIDER_UNAVAILABLE", 502, retryable=retryable) from error
            except Exception as error:
                raise failure("PROVIDER_UNAVAILABLE", 502) from error
            try:
                # Some compatible proxies ignore JSON mode and wrap the whole JSON.
                # Only unwrap one complete fence; schema validation remains mandatory.
                fenced = re.fullmatch(
                    r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", raw.strip(), re.DOTALL
                )
                if fenced:
                    raw = fenced.group(1)
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
            if self.finalize_result is not None:
                result = self.finalize_result(result)
                result = validate_result(self.intent, result.model_dump(mode="json"))
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={"validated_proposal": result.model_dump(mode="json")}
                ),
            )
            return
        raise failure("OUTPUT_VALIDATION_FAILED", 422)


def build_workflow(
    intent: Intent,
    agent: LlmAgent,
    revisions: int,
    validate_context: Callable[[], None],
    finalize_result: Callable[[AiResult], AiResult] | None = None,
) -> ProposalWorkflow:
    return ProposalWorkflow(
        name="proposal_workflow",
        intent=intent,
        revisions=revisions,
        sub_agents=[agent],
        validate_context=validate_context,
        finalize_result=finalize_result,
    )
