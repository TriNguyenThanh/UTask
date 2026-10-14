from django.db import transaction

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import (
    claim_receipt,
    lookup_receipt,
    replay_response,
    save_receipt,
)
from apps.projects.permissions import require_leader
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from infrastructure.integration import integration_client, source_error


def repository_data(project):
    return {
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
    emit_event(project, "project.repository.updated", repository_data(project))
    return True


def reconcile_connection(fact):
    """Called only with a verified Integration adapter result, not a client JSON body."""
    fact.validate()
    with transaction.atomic():
        project = lock_project(fact.project_id)
        return apply_connection_locked(project, fact, None)


def select_repository(actor, project_id, payload, scope, bearer):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        receipt = lookup_receipt(scope, payload)
        if receipt:
            return replay_response(receipt)
        if payload["expected_connection_generation"] != (project.github_connection_generation or 0):
            raise WorkError(
                "VERSION_CONFLICT",
                "Thông tin kết nối kho lưu trữ đã được cập nhật, vui lòng tải lại.",
                409,
            )
    # No Work lock/transaction is held across the provider owner's REST command.
    fact = integration_client().select_repository(
        project_id=project_id, actor=actor, bearer=bearer, **payload
    )
    fact.validate()
    if (
        fact.project_id != project_id
        or fact.operation_id != payload["operation_id"]
        or (fact.status != "DISCONNECTED" and fact.repo_id != payload["github_repo_id"])
    ):
        raise source_error("Thông tin kết nối kho mã nguồn không khớp với yêu cầu của bạn.")
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        receipt, fresh = claim_receipt(
            scope, payload, status=202 if fact.status == "PENDING" else 200
        )
        if not fresh:
            return replay_response(receipt)
        if payload["expected_connection_generation"] != (project.github_connection_generation or 0):
            # Another operation/source event won; do not overwrite it with this result.
            if project.github_operation_id != fact.operation_id:
                raise WorkError(
                    "VERSION_CONFLICT",
                    "Kết nối kho lưu trữ đã thay đổi trong quá trình xử lý liên kết.",
                    409,
                )
        if (fact.generation, fact.source_version) < (
            project.github_connection_generation or 0,
            project.github_connection_version or 0,
        ):
            raise WorkError(
                "VERSION_CONFLICT",
                "Thông tin kết nối kho mã nguồn đã cũ. Vui lòng tải lại dữ liệu mới nhất.",
                409,
            )
        apply_connection_locked(project, fact, actor.id)
        return save_receipt(
            scope,
            payload,
            repository_data(project),
            status=202 if fact.status == "PENDING" else 200,
            message={
                "PENDING": "Yêu cầu kết nối kho mã nguồn đang chờ xác nhận.",
                "CONNECTED": "Đã kết nối kho mã nguồn của dự án.",
                "DISCONNECTED": "Đã ngắt kết nối kho mã nguồn của dự án.",
            }[fact.status],
        )
