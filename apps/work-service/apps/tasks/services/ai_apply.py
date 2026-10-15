from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.messaging.services import (
    claim_receipt,
    emit_event,
    emit_events,
    payload_hash,
    record_activities,
    replay_response,
    save_receipt,
)
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task, TaskRelation
from apps.tasks.permissions import require_member_fields, require_task_writer
from apps.tasks.serializers.events import AIProposalAppliedEventSerializer
from apps.tasks.services.creation import create_tasks_locked
from apps.tasks.services.hierarchy import subtask_payload
from apps.tasks.services.mutations import check_version, lock_task
from apps.tasks.services.relations import check_cycles, relation_data
from common.content import clean_content
from common.errors import WorkError
from infrastructure.ai import VerifiedProposal


def approved_item_hash(project_id, parent_id, item):
    content = {
        key: value
        for key, value in item.items()
        if key not in {"local_id", "ai_revision", "dependencies"}
    }
    if "description_html" in content:
        content["description_html"] = clean_content(content["description_html"])[0]
    for field in ["assignee_ids", "label_ids"]:
        if field in content:
            content[field] = sorted(set(content[field]))
    return payload_hash(
        {
            "project_id": str(project_id),
            "parent_id": str(parent_id) if parent_id else None,
            "action": "create_subtask" if parent_id else "create_backlog",
            "revision": item["ai_revision"],
            "content": content,
            "dependencies": sorted(set(item.get("dependencies", []))),
        }
    )


def apply_tasks(actor, project_id, payload, scope, proof, *, parent_id=None):
    kind = "SUBTASK" if parent_id else "BACKLOG"
    item_field = "subtasks" if parent_id else "tasks"
    items = payload[item_field]
    with transaction.atomic():
        if parent_id:
            project, parent = lock_task(parent_id)
            if project.pk != project_id:
                raise WorkError("INVALID_OPERATION", "Công việc cha không thuộc cùng dự án.")
            member = require_task_writer(project, actor, parent)
            for item in items:
                require_member_fields(
                    member,
                    item,
                    {
                        "local_id",
                        "ai_revision",
                        "dependencies",
                        "title",
                        "description_html",
                        "acceptance_criteria",
                    },
                )
        else:
            project = lock_project(project_id)
            parent = None
            member = require_task_writer(project, actor, leader_only=True)
        receipt, fresh = claim_receipt(scope, payload, status=201)
        if not fresh:
            return replay_response(receipt)
        local_ids = [item["local_id"] for item in items]
        if len(local_ids) != len(set(local_ids)):
            raise WorkError(
                "VALIDATION_ERROR",
                "Mỗi công việc trong đề xuất phải có mã riêng, không được trùng nhau.",
            )
        existing = {
            row.ai_local_id: row
            for row in Task.objects.filter(project=project, ai_proposal_id=payload["proposal_id"])
        }
        mapping = {local_id: row.pk for local_id, row in existing.items()}
        new_items = []
        hashes = {}
        for item in items:
            local_id = item["local_id"]
            digest = approved_item_hash(project.pk, parent_id, item)
            hashes[local_id] = digest
            if local_id in existing:
                row = existing[local_id]
                if row.ai_payload_hash != digest or row.parent_id != parent_id:
                    raise WorkError(
                        "AI_ITEM_PAYLOAD_CONFLICT",
                        "Nội dung đề xuất này đã được áp dụng trước đó với thông tin khác.",
                        422,
                    )
            else:
                mapping[local_id] = uuid4()
                new_items.append(item)
        for item in items:
            if any(
                ref not in mapping or ref == item["local_id"]
                for ref in item.get("dependencies", [])
            ):
                raise WorkError("VALIDATION_ERROR", "Tham chiếu phụ thuộc cục bộ không hợp lệ.")
        if new_items:
            if not isinstance(proof, VerifiedProposal):
                raise WorkError(
                    "AI_PROVENANCE_INVALID", "Đề xuất chưa được xác minh tính hợp lệ.", 422
                )
            proof.validate(
                actor, project.pk, payload, kind, parent_id=parent_id, item_field=item_field
            )
            if parent:
                check_version(parent, payload["expected_parent_version"])
            elif project.version != payload["expected_project_version"]:
                raise WorkError(
                    "VERSION_CONFLICT", "Dự án đã có thay đổi, vui lòng tải lại dữ liệu.", 409
                )
            prepared = []
            for item in new_items:
                values = {
                    key: value
                    for key, value in item.items()
                    if key not in {"local_id", "ai_revision", "dependencies"}
                }
                if parent:
                    values = subtask_payload(project, actor, parent, member, values)
                values.update(
                    ai_proposal_id=payload["proposal_id"],
                    ai_local_id=item["local_id"],
                    ai_revision=item["ai_revision"],
                    ai_payload_hash=hashes[item["local_id"]],
                )
                prepared.append(values)
            create_tasks_locked(
                project,
                actor,
                prepared,
                source="AI_DECOMPOSED" if parent else "AI_BACKLOG",
                task_ids=[mapping[item["local_id"]] for item in new_items],
            )
            edges = [
                (mapping[dependency], mapping[item["local_id"]])
                for item in new_items
                for dependency in sorted(set(item.get("dependencies", [])))
            ]
            if edges:
                ids = {value for edge in edges for value in edge}
                live = set(
                    Task.objects.filter(
                        project=project,
                        pk__in=ids,
                        deleted_at__isnull=True,
                        archived_at__isnull=True,
                    ).values_list("id", flat=True)
                )
                if ids != live:
                    raise WorkError(
                        "INVALID_OPERATION", "Công việc phụ thuộc đã bị xóa hoặc đưa vào lưu trữ."
                    )
                check_cycles(project, edges)
                relations = TaskRelation.objects.bulk_create(
                    [
                        TaskRelation(task_id=source, related_task_id=target, relation_type="BLOCKS")
                        for source, target in edges
                    ]
                )
                targets = Task.objects.in_bulk({target for _, target in edges})
                activities, events = [], []
                for relation in relations:
                    task = targets[relation.related_task_id]
                    task.version += 1
                    task.updated_at = timezone.now()
                    relation_fact = relation_data(relation, project.pk)
                    activities.append(
                        {
                            "subject": task,
                            "actor_id": actor.id,
                            "verb": "created",
                            "field": "relation",
                            "new": relation_fact,
                        }
                    )
                    events.append(
                        {
                            "event_type": "task.relation.created",
                            "data": relation_fact,
                            "aggregate_type": "task",
                            "aggregate_id": task.pk,
                            "entity_version": task.version,
                        }
                    )
                Task.objects.bulk_update(list(targets.values()), ["version", "updated_at"])
                project.board_revision += len(relations)
                project.save(update_fields=["board_revision"])
                record_activities(activities)
                emit_events(project, events)
        tasks = Task.objects.select_related("project").in_bulk(
            [mapping[item["local_id"]] for item in items]
        )
        data = {
            "operation_id": str(receipt.operation_id),
            "project_id": str(project.pk),
            "parent_task_id": str(parent_id) if parent_id else None,
            "proposal_id": payload["proposal_id"],
            "source": "AI_DECOMPOSED" if parent else "AI_BACKLOG",
            "created_count": len(new_items),
            "affected_tasks": [
                {
                    "id": str(mapping[item["local_id"]]),
                    "local_id": item["local_id"],
                    "code": f"{project.identifier}-{tasks[mapping[item['local_id']]].sequence_id}",
                    "version": tasks[mapping[item["local_id"]]].version,
                    "ai_revision": item["ai_revision"],
                    "approved_payload_hash": hashes[item["local_id"]],
                }
                for item in items
            ],
            "committed_at": timezone.now().isoformat(),
        }
        if new_items:
            emit_event(
                project,
                "work.ai_proposal.applied",
                AIProposalAppliedEventSerializer({**data, "actor_user_id": str(actor.id)}).data,
                aggregate_type="project",
            )
        return save_receipt(
            scope,
            payload,
            data,
            status=201,
            message="Đã tạo các công việc từ đề xuất đã duyệt."
            if new_items
            else "Các công việc trong đề xuất đã được tạo trước đó; không tạo thêm công việc.",
        )
