from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import yaml

from application.responses import failed_response
from errors import failure
from models import QueuedAiResponse

CONTRACT = yaml.safe_load(
    (Path(__file__).parents[3] / "contracts/api/ai-service-v1.yaml").read_text()
)


def validate(name, body):
    jsonschema.Draft202012Validator(
        {**CONTRACT, "$ref": "#/components/schemas/" + name},
        format_checker=jsonschema.FormatChecker(),
    ).validate(body)


def test_queued_and_failed_envelopes_match_v1(payload):
    now = datetime.now(UTC)
    rid = uuid4()
    queued = QueuedAiResponse(
        request_id=rid,
        intent=payload.intent,
        status="queued",
        output_schema_version=payload.output_schema_version,
        created_at=now,
        status_url="/api/ai/v1/requests/" + str(rid),
    )
    validate("QueuedAiResponse", queued.model_dump(mode="json", exclude_none=True))
    for reason in [
        "BUDGET_EXCEEDED",
        "QUEUE_TIMEOUT",
        "DISPATCH_FAILED",
        "AUTH_UNAVAILABLE",
        "CONTEXT_STALE",
        "OUTPUT_VALIDATION_FAILED",
    ]:
        failed = failed_response(payload, rid, now, now, failure(reason))
        validate("FailedAiResponse", failed.model_dump(mode="json", exclude_none=True))
        validate(
            "ErrorResponse", {"error": failed.error.model_dump(mode="json", exclude_none=True)}
        )
