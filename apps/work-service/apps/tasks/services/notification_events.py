from apps.messaging.services import emit_event


def notification_task_data(task, actor_id, data, *, recipients=None):
    active = set(task.project.members.filter(status="ACTIVE").values_list("user_id", flat=True))
    assigned = {row.user_id for row in task.assignments.all()}
    recipients = assigned if recipients is None else set(recipients) & assigned
    return {
        **data,
        "actor_user_id": str(actor_id),
        "recipient_ids": [str(value) for value in sorted((recipients & active) - {actor_id})],
    }


def emit_assignment(project, task, actor_id, recipients):
    if not recipients:
        return
    data = notification_task_data(task, actor_id, {"task_id": str(task.pk)}, recipients=recipients)
    if data["recipient_ids"]:
        emit_event(
            project,
            "task.assigned",
            data,
            aggregate_type="task",
            aggregate_id=task.pk,
            entity_version=task.version,
        )
