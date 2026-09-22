from datetime import date

from app.agents.priority_analyzer.analyzer import suggest_priority
from app.agents.project_risk_analyzer.analyzer import analyze_project_risk
from app.agents.workload_analyzer.analyzer import analyze_workload
from app.core.settings import DATASETS_DIR
from app.schemas.models import PrioritySuggestionRequest
from app.tools.context_provider import DatasetContextProvider


def test_workload_golden_dataset_detects_overload():
    context = DatasetContextProvider(DATASETS_DIR).get_project_context("project-ai-first")
    output = analyze_workload(context)
    assert output.status == "IMBALANCED"
    assert [member.user_id for member in output.members if member.status == "OVERLOADED"] == [
        "user-ana"
    ]


def test_priority_uses_deadline_context():
    context = DatasetContextProvider(DATASETS_DIR).get_project_context("project-ai-first")
    output = suggest_priority(
        PrioritySuggestionRequest(task=context.tasks[0], project=context), today=date(2026, 9, 21)
    )
    assert output.suggested_priority.value == "HIGH"


def test_risk_output_is_grounded_in_structured_context():
    provider = DatasetContextProvider(DATASETS_DIR)
    output = analyze_project_risk(
        provider.get_project_context("project-ai-first"),
        provider.get_github_activity("project-ai-first"),
        today=date(2026, 9, 25),
    )
    assert any(factor.code == "OVERDUE_TASKS" for factor in output.factors)
