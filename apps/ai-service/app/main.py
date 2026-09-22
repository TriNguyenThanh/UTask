from fastapi import FastAPI, HTTPException, Query

from app.agents.priority_analyzer.analyzer import suggest_priority
from app.agents.project_risk_analyzer.analyzer import analyze_project_risk
from app.agents.task_generator.generator import ModelRuntimeNotConfigured, generate_tasks
from app.agents.workload_analyzer.analyzer import analyze_workload
from app.core.settings import DATASETS_DIR, INTEGRATION_SERVICE_URL, WORK_SERVICE_URL
from app.schemas.models import (
    PrioritySuggestion,
    PrioritySuggestionRequest,
    ProjectRiskAnalysis,
    TaskGenerationRequest,
    TaskGenerationSuggestion,
    WorkloadAnalysis,
)
from app.tools.context_provider import DatasetContextProvider, HttpContextProvider

app = FastAPI(title="UTask AI Service", version="v1")


def provider(source: str):
    if source == "service":
        if not WORK_SERVICE_URL or not INTEGRATION_SERVICE_URL:
            raise HTTPException(
                status_code=503,
                detail="Work and Integration service URLs are required for service context.",
            )
        return HttpContextProvider(WORK_SERVICE_URL, INTEGRATION_SERVICE_URL)
    return DatasetContextProvider(DATASETS_DIR)


@app.get("/healthz")
def healthz():
    return {"service": "ai-service", "status": "ok"}


@app.post("/api/v1/ai/workload-analysis", response_model=WorkloadAnalysis)
def workload_analysis(
    project_id: str, source: str = Query("dataset", pattern="^(dataset|service)$")
):
    return analyze_workload(provider(source).get_project_context(project_id))


@app.post("/api/v1/ai/project-risk-analysis", response_model=ProjectRiskAnalysis)
def project_risk_analysis(
    project_id: str, source: str = Query("dataset", pattern="^(dataset|service)$")
):
    context = provider(source)
    return analyze_project_risk(
        context.get_project_context(project_id), context.get_github_activity(project_id)
    )


@app.post("/api/v1/ai/priority-suggestion", response_model=PrioritySuggestion)
def priority_suggestion(request: PrioritySuggestionRequest):
    return suggest_priority(request)


@app.post("/api/v1/ai/generate-tasks", response_model=TaskGenerationSuggestion)
def task_generation(request: TaskGenerationRequest):
    try:
        return generate_tasks(request)
    except ModelRuntimeNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
