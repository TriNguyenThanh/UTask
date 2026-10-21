from django.db import transaction

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from infrastructure.integration import source_error


def repository_data(project, *, include_pending=True):
    from apps.integrations.services.operations import command_generation, pending_operation

    data = {
        "project_id": str(project.pk),
        "github_repo_id": project.github_repo_id,
        "github_repo_owner": project.github_repo_owner,
        "github_repo_name": project.github_repo_name,
        "github_default_branch": project.github_default_branch,
        "operation_id": project.github_operation_id,
        "status": project.github_connection_status,
        "connection_generation": project.github_connection_generation,
        "source_version": project.github_connection_version,
        "synced_at": project.github_synced_at.isoformat() if project.github_synced_at else None,
    }
    data["command_generation"] = command_generation(project)
    pending = pending_operation(project) if include_pending else None
    if pending and pending.state != "ABORT":
        data["status"] = "PENDING"
        data["operation_id"] = pending.operation_id
        if pending.prepared:
            for output, source in [
                ("github_repo_id", "repo_id"),
                ("github_repo_owner", "repo_owner"),
                ("github_repo_name", "repo_name"),
                ("github_default_branch", "default_branch"),
                ("connection_generation", "generation"),
                ("source_version", "source_version"),
                ("synced_at", "synced_at"),
            ]:
                data[output] = pending.prepared[source]
    return data


def apply_connection_locked(project, fact, actor_id):
    fact.validate()
    if fact.project_id != project.pk:
        raise source_error("Thông tin kết nối kho lưu trữ không đúng với dự án.")
    current = (project.github_connection_generation or 0, project.github_connection_version or 0)
    incoming = (fact.generation, fact.source_version)
    if incoming < current:
        return False
    fields = {
        "github_repo_id": fact.repo_id,
        "github_repo_owner": fact.repo_owner,
        "github_repo_name": fact.repo_name,
        "github_default_branch": fact.default_branch,
        "github_operation_id": fact.operation_id,
        "github_connection_status": fact.status,
        "github_connection_generation": fact.generation,
        "github_connection_version": fact.source_version,
    }
    changes = {field: value for field, value in fields.items() if getattr(project, field) != value}
    if incoming == current and project.github_connection_version is not None and changes:
        raise WorkError(
            "SOURCE_VERSION_CONFLICT",
            "Thông tin kết nối kho mã nguồn đã thay đổi. Vui lòng tải lại dữ liệu.",
            409,
        )
    if not changes:
        return False
    for field, value in changes.items():
        record_activity(
            project, actor_id, "updated", field=field, old=getattr(project, field), new=value
        )
        setattr(project, field, value)
    project.github_synced_at = fact.synced_at
    project.version += 1
    project.save()
    emit_event(
        project, "project.repository.updated", repository_data(project, include_pending=False)
    )
    return True


def reconcile_connection(fact):
    """Called only with a verified Integration adapter result, not a client JSON body."""
    fact.validate()
    with transaction.atomic():
        project = lock_project(fact.project_id)
        return apply_connection_locked(project, fact, None)


def select_repository(actor, project_id, payload, scope, bearer):
    from apps.integrations.services.operations import start_operation

    return start_operation(actor, project_id, payload, scope, bearer)
