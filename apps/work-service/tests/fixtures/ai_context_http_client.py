"""Tiến trình test dùng adapter AI thật; credential chỉ nhận qua stdin."""

import asyncio
import json
import sys


async def main():
    payload = json.load(sys.stdin)
    # Separate interpreter/process avoids Django's config/infrastructure module names.
    sys.path.insert(0, payload["ai_source"])
    import httpx
    from errors import ServiceError
    from infrastructure.context_factory import build_context_adapter
    from models import CreateAiRequest
    from models.security import Principal
    from pydantic import SecretStr, TypeAdapter

    from config import Settings

    base = payload["base"] + "/api/v1/internal/ai/targets/{target_type}/{target_id}"
    settings = Settings(
        _env_file=None,
        environment="test",
        mock_test=False,
        authorization_urls={kind: base + "/authorize" for kind in payload["targets"]},
        context_urls={
            f"{kind}:{domain}": base + "/contexts/" + domain
            for kind in payload["targets"]
            for domain in ("project", "team", "progress", "task")
            if domain != "task" or kind == "task"
        },
        work_service_key=SecretStr(payload["key"]),
    )
    principal = Principal(payload["user_id"], payload["token"])
    checked = 0
    async with httpx.AsyncClient(trust_env=False) as client:
        adapter = build_context_adapter(settings, client)
        for kind, target_id in payload["targets"].items():
            request = TypeAdapter(CreateAiRequest).validate_python(
                {
                    "intent": "task_decomposition" if kind == "task" else "risk_analysis",
                    "target": {"type": kind, "id": target_id},
                    "input": {},
                }
            )
            if payload.get("deny"):
                try:
                    await adapter.authorize(principal, request)
                except ServiceError as error:
                    assert error.code == "TARGET_ACCESS_DENIED"
                    checked += 1
                    continue
                raise AssertionError("Caller unexpectedly obtained access")
            await adapter.authorize(principal, request)
            for domain in ("project", "team", "progress", "task"):
                if domain == "task" and kind != "task":
                    continue
                document = await adapter.fetch(domain, principal, request)
                assert document.domain == domain
                assert document.status in {"available", "partial"}
                checked += 1
    print(json.dumps({"checked": checked, "adapter": "InternalContextAdapter"}))


if __name__ == "__main__":
    asyncio.run(main())
