from datetime import UTC, date, datetime

from app.schemas.models import GitHubActivity, ProjectContext, ProjectRiskAnalysis, RiskFactor


def analyze_project_risk(
    project: ProjectContext, activity: GitHubActivity, today: date | None = None
) -> ProjectRiskAnalysis:
    today = today or datetime.now(UTC).date()
    factors = []
    overdue = [
        task
        for task in project.tasks
        if task.due_date and task.due_date < today and task.status != "DONE"
    ]
    if overdue:
        factors.append(
            RiskFactor(
                code="OVERDUE_TASKS",
                explanation=f"{len(overdue)} unfinished task(s) are past their due date.",
            )
        )
    done_tasks = [task for task in project.tasks if task.status == "DONE"]
    if done_tasks and not activity.commits and not activity.pull_requests:
        factors.append(
            RiskFactor(
                code="MISSING_GITHUB_ACTIVITY",
                explanation="Completed tasks have no normalized GitHub commit or pull-request activity.",
            )
        )
    return ProjectRiskAnalysis(
        status="AT_RISK" if factors else "ON_TRACK",
        factors=factors,
        explanation="Risk factors are grounded in task deadlines/status and normalized GitHub activity.",
    )
