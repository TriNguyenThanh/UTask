"""ADK runtime/provider adapter; model cấu hình ngoài nghiệp vụ."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from application.ports import StoredRequest
from config import Settings
from context.tools import ContextToolPool
from errors import ServiceError, failure
from models import CreateAiRequest, SucceededAiResponse
from models.security import Principal
from models.validation import validate_result
from workflow.bounded import build_workflow
from workflow.instructions import build_instruction
from workflow.ports import Charge, ContextGateway


class AdkRuntime:
    def __init__(self, settings: Settings, model: BaseLlm | None = None):
        self.settings = settings
        self.model = model

    async def run(
        self,
        request_id: UUID,
        payload: CreateAiRequest,
        created_at: datetime,
        pool: ContextToolPool,
        charge: Charge,
        deadline: datetime,
    ) -> SucceededAiResponse:
        settings = self.settings
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise failure("WORKFLOW_TIMEOUT", 504)

        output_allowance = settings.max_output_tokens

        async def before_model(callback_context, llm_request):
            nonlocal output_allowance
            output_allowance = await charge("output", settings.max_output_tokens, 0)
            if output_allowance <= 0:
                raise failure("BUDGET_EXCEEDED", 429)
            llm_request.config.max_output_tokens = output_allowance
            await charge("model", settings.max_model_calls)

        async def after_model(callback_context, llm_response):
            usage = llm_response.usage_metadata
            # Khi SDK thiếu usage, trừ toàn bộ cap; không cho budget trở thành vô hạn.
            tokens = (
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage and usage.candidates_token_count is not None
                else output_allowance
            )
            await charge("output", settings.max_output_tokens, tokens)

        agent = LlmAgent(
            name="domain_agent",
            model=self.model
            or Gemini(model=settings.model, retry_options=types.HttpRetryOptions(attempts=1)),
            instruction=build_instruction(payload),
            tools=pool.tools(),
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=settings.max_output_tokens,
                temperature=0.2,
                http_options=types.HttpOptions(
                    timeout=int(remaining * 1000), retry_options=types.HttpRetryOptions(attempts=1)
                ),
            ),
            before_model_callback=before_model,
            after_model_callback=after_model,
        )
        # Schema validation do workflow sở hữu để có thể revise và phối hợp domain tools.
        workflow = build_workflow(
            payload.intent, agent, settings.max_revisions, pool.validate_context
        )
        sessions = InMemorySessionService()
        session = await sessions.create_session(
            app_name="utask_ai", user_id="requester", session_id=str(request_id)
        )
        runner = Runner(app_name="utask_ai", agent=workflow, session_service=sessions)
        prompt = payload.model_dump_json(by_alias=True)
        try:
            async with asyncio.timeout(remaining):
                async for _event in runner.run_async(
                    user_id=session.user_id,
                    session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
                    run_config=RunConfig(max_llm_calls=settings.max_model_calls),
                ):
                    pass
                saved = await sessions.get_session(
                    app_name="utask_ai", user_id=session.user_id, session_id=session.id
                )
                result = validate_result(payload.intent, saved.state.get("validated_proposal"))
                return SucceededAiResponse(
                    request_id=request_id,
                    intent=payload.intent,
                    status="succeeded",
                    output_schema_version=payload.output_schema_version,
                    created_at=created_at,
                    updated_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    result=result,
                    context=pool.metadata(),
                )
        except TimeoutError as error:
            raise failure("WORKFLOW_TIMEOUT", 504) from error
        except ServiceError:
            raise
        except Exception as error:
            raise failure("PROVIDER_UNAVAILABLE", 502, retryable=True) from error
        finally:
            await runner.close()


class AdkRequestExecutor:
    def __init__(self, runtime: AdkRuntime, gateway: ContextGateway):
        self.runtime = runtime
        self.gateway = gateway

    async def execute(
        self, stored: StoredRequest, principal: Principal, charge: Charge
    ) -> SucceededAiResponse:
        pool = ContextToolPool(
            self.gateway,
            principal,
            stored.payload,
            charge,
            self.runtime.settings.max_context_tool_calls,
        )
        return await self.runtime.run(
            stored.request_id,
            stored.payload,
            stored.response.created_at,
            pool,
            charge,
            stored.deadline,
        )
