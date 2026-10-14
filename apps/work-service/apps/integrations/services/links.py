from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.integrations.models import TaskGitHubLink
from apps.integrations.serializers.links import GitHubLinkSerializer
from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import (
    claim_receipt,
    lookup_receipt,
    replay_response,
    save_receipt,
)
from apps.projects.permissions import active_member
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from common.errors import WorkError
from common.responses import success_response
from infrastructure.integration import integration_client, source_error


def require_link_writer(project, actor, task):
    if active_member(project, actor) is None:
        raise NotFound("Không tìm thấy công việc hoặc dự án yêu cầu.")
    if project.archived_at or project.deleted_at or task.archived_at or task.deleted_at:
        raise WorkError("INVALID_OPERATION", "Công việc hoặc dự án đang ở chế độ chỉ đọc.")


def lock_subject(task_id):
    project_id = Task.objects.filter(pk=task_id).values_list("project_id", flat=True).first()
    if project_id is None:
        raise NotFound("Không tìm thấy công việc yêu cầu.")
    project = lock_project(project_id)
    task = Task.objects.select_for_update().get(pk=task_id, project=project)
    return project, task


def require_connection(project, fact=None):
    if project.github_connection_status != "CONNECTED" or not project.github_repo_id:
        raise WorkError(
            "INVALID_OPERATION", "Dự án chưa được kết nối với kho lưu trữ mã nguồn nào."
        )
    if fact and (
        fact.project_id != project.pk
        or fact.repo_id != project.github_repo_id
        or fact.generation != project.github_connection_generation
    ):
        raise WorkError(
            "VERSION_CONFLICT",
            "Liên kết thuộc kết nối kho lưu trữ đã cũ hoặc không đúng phạm vi dự án.",
            409,
        )


def metadata_values(fact):
    return {
        "connection_generation": fact.generation,
        "source_version": fact.source_version,
        "github_title": fact.title,
        "github_status": fact.status,
        "github_url": fact.url,
        "is_verified": fact.is_verified,
        "synced_at": fact.synced_at,
    }


def link_event(project, task, link, actor_id, verb):
    data = GitHubLinkSerializer(link).data
    record_activity(task, actor_id, verb, field="github_links", new=data)
    emit_event(
        project,
        "task.github_link." + verb,
        data,
        aggregate_type="task",
        aggregate_id=task.pk,
        entity_version=task.version,
    )


def ingest_reference(task_id, fact, *, allow_relink=False):
    fact.validate()
    with transaction.atomic():
        project, task = lock_subject(task_id)
        if task.deleted_at or project.deleted_at:
            raise NotFound("Không tìm thấy công việc yêu cầu.")
        require_connection(project, fact)
        link = (
            TaskGitHubLink.objects.select_for_update()
            .filter(
                task=task,
                github_repo_id=fact.repo_id,
                link_type=fact.link_type,
                github_ref_id=fact.ref_id,
                deleted_at__isnull=True,
            )
            .first()
        )
        if link:
            incoming = (fact.generation, fact.source_version)
            current = (link.connection_generation, link.source_version)
            if incoming < current:
                return link, False
            values = metadata_values(fact)
            changed = any(
                getattr(link, field) != value
                for field, value in values.items()
                if field != "synced_at"
            )
            if incoming == current and changed:
                raise WorkError(
                    "SOURCE_VERSION_CONFLICT",
                    "Thông tin liên kết GitHub đã thay đổi. Vui lòng tải lại dữ liệu.",
                    409,
                )
            if not changed:
                return link, False
            for field, value in values.items():
                setattr(link, field, value)
            link.save()
            link_event(project, task, link, None, "updated")
            return link, True
        tombstone = (
            TaskGitHubLink.objects.filter(
                task=task,
                github_repo_id=fact.repo_id,
                link_type=fact.link_type,
                github_ref_id=fact.ref_id,
                deleted_at__isnull=False,
            )
            .order_by("-connection_generation", "-source_version")
            .first()
        )
        if (
            not allow_relink
            and tombstone
            and (fact.generation, fact.source_version)
            <= (tombstone.connection_generation, tombstone.source_version)
        ):
            return tombstone, False
        link = TaskGitHubLink.objects.create(
            task=task,
            github_repo_id=fact.repo_id,
            link_type=fact.link_type,
            github_ref_id=fact.ref_id,
            **metadata_values(fact),
        )
        link_event(project, task, link, None, "candidate_created")
        return link, True


def confirm_link_locked(project, task, link, actor):
    if (
        link.github_repo_id != project.github_repo_id
        or link.connection_generation != project.github_connection_generation
    ):
        raise WorkError(
            "VERSION_CONFLICT", "Đề xuất liên kết thuộc kết nối kho lưu trữ đã cũ.", 409
        )
    require_connection(project)
    if link.confirmation_status == "CONFIRMED":
        return False
    if not link.is_verified:
        raise WorkError("INVALID_OPERATION", "Chưa thể xác minh đề xuất liên kết GitHub này.")
    link.confirmation_status = "CONFIRMED"
    link.confirmed_by_user_id = actor.id
    link.confirmed_at = timezone.now()
    link.save(update_fields=["confirmation_status", "confirmed_by_user_id", "confirmed_at"])
    link_event(project, task, link, actor.id, "confirmed")
    return True


def confirm_link(actor, task_id, link_id, scope):
    body = {"task_id": str(task_id), "link_id": str(link_id)}
    with transaction.atomic():
        project, task = lock_subject(task_id)
        require_link_writer(project, actor, task)
        receipt, fresh = claim_receipt(scope, body)
        if not fresh:
            return replay_response(receipt)
        link = (
            TaskGitHubLink.objects.select_for_update()
            .filter(pk=link_id, task=task, deleted_at__isnull=True)
            .first()
        )
        if link is None:
            raise NotFound("Không tìm thấy liên kết yêu cầu.")
        confirm_link_locked(project, task, link, actor)
        return save_receipt(
            scope,
            body,
            GitHubLinkSerializer(link).data,
            message="Liên kết GitHub đã được xác nhận.",
        )


def manual_link(actor, task_id, payload, bearer, scope=None):
    with transaction.atomic():
        project, task = lock_subject(task_id)
        require_link_writer(project, actor, task)
        if scope and (receipt := lookup_receipt(scope, payload)):
            return replay_response(receipt)
        require_connection(project)
        facts = {
            "project_id": project.pk,
            "repo_id": project.github_repo_id,
            "generation": project.github_connection_generation,
        }
    fact = integration_client().verify_reference(actor=actor, bearer=bearer, **facts, **payload)
    fact.validate()
    if fact.link_type != payload["link_type"] or (
        fact.link_type == "PULL_REQUEST" and fact.ref_id != payload["github_ref_id"]
    ):
        raise source_error("Bằng chứng xác thực liên kết không khớp với yêu cầu chuẩn hóa.")
    with transaction.atomic():
        project, task = lock_subject(task_id)
        require_link_writer(project, actor, task)
        if scope:
            receipt, fresh = claim_receipt(scope, payload, status=201)
            if not fresh:
                return replay_response(receipt)
        require_connection(project, fact)
        link, _ = ingest_reference(task_id, fact, allow_relink=True)
        link.created_by_user_id = link.created_by_user_id or actor.id
        link.save(update_fields=["created_by_user_id"])
        confirm_link_locked(project, task, link, actor)
        data = GitHubLinkSerializer(link).data
        return (
            save_receipt(
                scope, payload, data, status=201, message="Liên kết GitHub đã được xác nhận."
            )
            if scope
            else success_response(data, status=201, message="Liên kết GitHub đã được xác nhận.")
        )


def unlink(actor, task_id, link_id):
    with transaction.atomic():
        project, task = lock_subject(task_id)
        require_link_writer(project, actor, task)
        link = (
            TaskGitHubLink.objects.select_for_update()
            .filter(pk=link_id, task=task, deleted_at__isnull=True)
            .first()
        )
        if link is None:
            raise NotFound("Không tìm thấy liên kết yêu cầu.")
        link.deleted_at = timezone.now()
        link.save(update_fields=["deleted_at"])
        link_event(project, task, link, actor.id, "unlinked")
        return success_response(
            {"unlinked_id": str(link.pk)}, message="Đã gỡ liên kết GitHub khỏi công việc."
        )
