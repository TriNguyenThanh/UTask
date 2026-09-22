from datetime import UTC, date, datetime

from app.schemas.models import Priority, PrioritySuggestion, PrioritySuggestionRequest


def suggest_priority(
    request: PrioritySuggestionRequest, today: date | None = None
) -> PrioritySuggestion:
    today = today or datetime.now(UTC).date()
    if request.task.due_date and (request.task.due_date - today).days <= 2:
        return PrioritySuggestion(
            suggested_priority=Priority.HIGH, explanation="The task deadline is within two days."
        )
    if request.task.priority == Priority.HIGH:
        return PrioritySuggestion(
            suggested_priority=Priority.HIGH,
            explanation="The current high priority is retained because no lower-risk context was provided.",
        )
    return PrioritySuggestion(
        suggested_priority=Priority.MEDIUM,
        explanation="No imminent deadline or dependency signal requires escalation.",
    )
