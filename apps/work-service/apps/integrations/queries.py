from apps.integrations.models import TaskGitHubLink
from apps.tasks.queries import visible_task


def task_github_links(actor, task_id):
    task = visible_task(actor, task_id)
    return TaskGitHubLink.objects.filter(task=task, deleted_at__isnull=True).order_by("id")
