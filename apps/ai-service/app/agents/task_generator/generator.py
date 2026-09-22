from app.schemas.models import TaskGenerationRequest, TaskGenerationSuggestion


class ModelRuntimeNotConfigured(RuntimeError):
    pass


def generate_tasks(_request: TaskGenerationRequest) -> TaskGenerationSuggestion:
    """Reserve this boundary for the Google ADK runtime; never invent model output."""
    raise ModelRuntimeNotConfigured("Google ADK model runtime is not configured.")
