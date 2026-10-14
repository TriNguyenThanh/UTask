from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.messaging.models import IdempotencyRecord
from apps.messaging.services import (
    claim_receipt,
    emit_event,
    lookup_receipt,
    payload_hash,
    replay_response,
    save_receipt,
)
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from apps.tasks.permissions import require_task_writer
from apps.tasks.serializers.events import AIProposalAppliedEventSerializer
from apps.tasks.services.bulk import bulk_sprint_scope
from apps.tasks.services.mutations import check_version, update_task
from common.errors import WorkError
from infrastructure.ai import VerifiedProposal


def approved_action_hash(project_id, payload):
    actions = [
        {
            key: value
            for key, value in row.items()
            if key not in {"expected_version", "expected_sprint_version"}
        }
        for row in payload["actions"]
    ]
    for action in actions:
        if "assignee_ids" in action:
            action["assignee_ids"] = sorted(set(action["assignee_ids"]))
    return payload_hash(
        {
            "project_id": str(project_id),
            "proposal_id": payload["proposal_id"],
            "item_id": payload["item_id"],
            "revision": payload["ai_revision"],
            "actions": actions,
        }
    )


def apply_actions(actor, project_id, payload, scope, proof):
    with transaction.atomic():
        project = lock_project(project_id)
        require_task_writer(project, actor, leader_only=True)
        receipt = lookup_receipt(scope, payload)
        if receipt:
            return replay_response(receipt)
        digest = approved_action_hash(project.pk, payload)
        previous = IdempotencyRecord.objects.filter(
            ai_proposal_id=payload["proposal_id"], ai_item_id=payload["item_id"]
        ).first()
        if previous:
            data = previous.response_body["data"]
            if data["project_id"] != str(project.pk):
                raise NotFound("Không tìm thấy thao tác đề xuất trí tuệ nhân tạo yêu cầu.")
            if data.get("approved_payload_hash") != digest:
                raise WorkError(
                    "AI_ITEM_PAYLOAD_CONFLICT",
                    "Hành động này đã được áp dụng trước đó với nội dung khác.",
                    422,
                )
            return replay_response(previous)
        if not isinstance(proof, VerifiedProposal):
            raise WorkError(
                "AI_PROVENANCE_INVALID", "Hành động chưa được xác thực tính hợp lệ.", 422
            )
        proof.validate(actor, project.pk, payload, "ACTION")
        receipt, _ = claim_receipt(scope, payload)
        receipt.ai_proposal_id = payload["proposal_id"]
        receipt.ai_item_id = payload["item_id"]
        receipt.expires_at = None
        receipt.save(update_fields=["ai_proposal_id", "ai_item_id", "expires_at"])
        affected = set()
        for action in payload["actions"]:
            task_id = action["task_id"]
            task = Task.objects.filter(
                pk=task_id, project=project, deleted_at__isnull=True, archived_at__isnull=True
            ).first()
            if task is None:
                raise WorkError(
                    "INVALID_OPERATION",
                    "Công việc mục tiêu không thuộc phạm vi có quyền chỉnh sửa.",
                )
            kind = action["kind"]
            if kind == "SPRINT_SCOPE":
                check_version(task, action["expected_version"])
                bulk_sprint_scope(
                    project=project,
                    actor=actor,
                    task_ids=[task_id],
                    sprint_id=action["sprint_id"],
                    action=action["scope_action"],
                    reason=action["reason"],
                    expected_version=action["expected_sprint_version"],
                    operation_id=receipt.operation_id,
                )
            else:
                field = {
                    "SET_PRIORITY": "priority",
                    "SET_DEADLINE": "due_date",
                    "SET_ASSIGNEES": "assignee_ids",
                }[kind]
                update_task(
                    actor,
                    task_id,
                    {"expected_version": action["expected_version"], field: action[field]},
                )
            affected.add(task_id)
        tasks = Task.objects.filter(pk__in=affected).order_by("id")
        data = {
            "operation_id": str(receipt.operation_id),
            "project_id": str(project.pk),
            "parent_task_id": None,
            "proposal_id": payload["proposal_id"],
            "item_id": payload["item_id"],
            "source": "AI_ACTION",
            "created_count": 0,
            "approved_payload_hash": digest,
            "affected_tasks": [
                {
                    "id": str(row.pk),
                    "local_id": payload["item_id"],
                    "code": f"{project.identifier}-{row.sequence_id}",
                    "version": row.version,
                    "ai_revision": payload["ai_revision"],
                    "approved_payload_hash": digest,
                }
                for row in tasks
            ],
            "committed_at": timezone.now().isoformat(),
        }
        project.refresh_from_db()
        emit_event(
            project,
            "work.ai_proposal.applied",
            AIProposalAppliedEventSerializer({**data, "actor_user_id": str(actor.id)}).data,
        )
        return save_receipt(
            scope, payload, data, message="Đã áp dụng các thay đổi trong đề xuất đã duyệt."
        )
