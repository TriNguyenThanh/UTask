from django.db import transaction

from apps.messaging.services.audit import record_activity
from apps.messaging.services.outbox import emit_event
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from apps.projects.models import ProjectMember
from apps.projects.permissions import active_member, require_leader
from apps.projects.services.locking import lock_project
from common.errors import WorkError
from common.responses import success_response


def declare_username(actor, project_id, user_id, username):
    with transaction.atomic():
        project = lock_project(project_id)
        caller = active_member(project, actor)
        if caller is None or actor.id != user_id:
            raise WorkError(
                "PERMISSION_DENIED",
                "Bạn chỉ có thể khai báo tài khoản GitHub của mình khi còn là thành viên dự án.",
                403,
            )
        if project.archived_at:
            raise WorkError("INVALID_OPERATION", "Dự án đang ở chế độ chỉ đọc.")
        member = (
            ProjectMember.objects.select_for_update()
            .filter(project=project, user_id=user_id, status="ACTIVE")
            .first()
        )
        if member is None:
            raise WorkError(
                "MEMBER_NOT_ACTIVE", "Thành viên không còn ở trạng thái hoạt động.", 422
            )
        if member.is_github_verified and member.github_username != username:
            raise WorkError(
                "INVALID_OPERATION",
                "Liên kết tài khoản đã xác thực chỉ có thể thay đổi thông qua cổng ủy quyền OAuth.",
            )
        if member.github_username != username:
            record_activity(
                member,
                actor.id,
                "updated",
                field="github_username",
                old=member.github_username,
                new=username,
            )
            member.github_username = username
            member.save(update_fields=["github_username", "updated_at"])
            emit_event(
                project,
                "project.member.github_declared",
                {
                    "user_id": str(user_id),
                    "github_username": username,
                    "is_github_verified": member.is_github_verified,
                },
            )
        return success_response(
            {
                "user_id": str(user_id),
                "github_username": member.github_username,
                "is_github_verified": member.is_github_verified,
            },
            message="Đã ghi nhận tài khoản GitHub do bạn khai báo.",
        )


def apply_account_fact(fact):
    fact.validate()
    project_ids = list(
        ProjectMember.objects.filter(user_id=fact.user_id, status="ACTIVE")
        .order_by("project_id")
        .values_list("project_id", flat=True)
    )
    changed = 0
    with transaction.atomic():
        for project_id in project_ids:
            project = lock_project(project_id)
            member = (
                ProjectMember.objects.select_for_update()
                .filter(project=project, user_id=fact.user_id, status="ACTIVE")
                .first()
            )
            if member is None or (
                member.github_source_version is not None
                and fact.source_version <= member.github_source_version
            ):
                continue
            matching_id = member.github_user_id == fact.github_user_id
            matching_name = (
                member.github_username or ""
            ).casefold() == fact.github_username.casefold()
            if (fact.verified and not (matching_id or matching_name)) or (
                not fact.verified and not matching_id
            ):
                continue
            values = {
                "is_github_verified": fact.verified,
                "github_source_version": fact.source_version,
            }
            if fact.verified:
                values.update(
                    github_user_id=fact.github_user_id, github_username=fact.github_username
                )
            for field, value in values.items():
                if getattr(member, field) != value:
                    record_activity(
                        member, None, "updated", field=field, old=getattr(member, field), new=value
                    )
                    setattr(member, field, value)
            member.save()
            emit_event(
                project,
                "project.member.github_mapping_updated",
                {"user_id": str(fact.user_id), **values},
            )
            changed += 1
    return changed


def request_verification(actor, project_id, user_id, scope):
    with transaction.atomic():
        project = lock_project(project_id)
        require_leader(project, actor)
        body = {"user_id": str(user_id)}
        receipt, fresh = claim_receipt(scope, body)
        if not fresh:
            return replay_response(receipt)
        member = ProjectMember.objects.filter(
            project=project, user_id=user_id, status="ACTIVE"
        ).first()
        if member is None:
            raise WorkError(
                "MEMBER_NOT_ACTIVE", "Thành viên không còn ở trạng thái hoạt động.", 422
            )
        data = {
            "project_id": str(project.pk),
            "user_id": str(user_id),
            "requested_by_user_id": str(actor.id),
        }
        record_activity(member, actor.id, "github_verification_requested")
        emit_event(project, "project.member.github_verification_requested", data)
        return save_receipt(
            scope,
            body,
            data,
            message="Đã ghi nhận yêu cầu nhắc thành viên xác minh tài khoản GitHub.",
        )
