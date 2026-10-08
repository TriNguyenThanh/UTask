"""Kiểm tra output theo đúng intent, không chấp nhận union sai ngữ nghĩa."""

from pydantic import BaseModel

from .common import Intent
from .results import BacklogResult, RiskAnalysisResult, TaskDecompositionResult

RESULT_SCHEMAS: dict[Intent, type[BaseModel]] = {
    Intent.BACKLOG_GENERATION: BacklogResult,
    Intent.TASK_DECOMPOSITION: TaskDecompositionResult,
    Intent.RISK_ANALYSIS: RiskAnalysisResult,
}


def validate_result(intent: Intent, raw: object):
    schema = RESULT_SCHEMAS[intent]
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json")
    return schema.model_validate_json(raw) if isinstance(raw, str) else schema.model_validate(raw)
