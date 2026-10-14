from uuid import uuid4

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.messaging.services import (
    claim_receipt,
    emit_events,
    record_activities,
    replay_response,
    save_receipt,
)
from apps.projects.models import ProjectMember, State
from apps.projects.services.locking import lock_project
from apps.tasks.models import Epic, Label, Task, TaskAssignment, TaskLabel
from apps.tasks.permissions import require_task_writer
from apps.tasks.queries import task_queryset
from apps.tasks.serializers.presentation import serialize_tasks
from apps.tasks.services.allocation import allocate_sequences
from common.content import clean_content
from common.errors import WorkError


def load_link_facts(project, items):
    state_ids = {item["state_id"] for item in items if item.get("state_id")}
    state_scope = Q(pk__in=state_ids)
    if any(not item.get("state_id") for item in items):
        state_scope |= Q(is_default=True)
    states = list(
        State.objects.filter(state_scope, project=project, deleted_at__isnull=True).order_by("id")
    )
    epic_ids = {item["epic_id"] for item in items if item.get("epic_id")}
    assignee_ids = {user_id for item in items for user_id in item.get("assignee_ids", [])}
    label_ids = {label_id for item in items for label_id in item.get("label_ids", [])}
    return {
        "states": {state.pk: state for state in states},
        "default_state": next((state for state in states if state.is_default), None),
        "epics": set(
            Epic.objects.filter(
                project=project, pk__in=epic_ids, deleted_at__isnull=True
            ).values_list("pk", flat=True)
        ),
        "assignees": set(
            ProjectMember.objects.filter(
                project=project, user_id__in=assignee_ids, status="ACTIVE"
            ).values_list("user_id", flat=True)
        ),
        "labels": set(
            Label.objects.filter(
                project=project, pk__in=label_ids, deleted_at__isnull=True
            ).values_list("pk", flat=True)
        ),
    }


def validate_links(project, payload, *, facts=None):
    facts = facts if facts is not None else load_link_facts(project, [payload])
    state = (
        facts["states"].get(payload["state_id"])
        if payload.get("state_id")
        else facts["default_state"]
    )
    if state is None:
        raise WorkError(
            "VALIDATION_ERROR", "Trạng thái công việc phải đang hoạt động trong cùng dự án.", 422
        )
    epic_id = payload.get("epic_id")
    if epic_id and epic_id not in facts["epics"]:
        raise WorkError(
            "VALIDATION_ERROR", "Mục tiêu lớn (epic) không thuộc dự án hoặc đã bị xóa.", 422
        )
    assignees = set(payload.get("assignee_ids", []))
    if not assignees <= facts["assignees"]:
        raise WorkError(
            "MEMBER_NOT_ACTIVE",
            "Người phụ trách phải là thành viên đang hoạt động trong cùng dự án.",
            422,
        )
    labels = set(payload.get("label_ids", []))
    if not labels <= facts["labels"]:
        raise WorkError("VALIDATION_ERROR", "Nhãn công việc không thuộc dự án hoặc đã bị xóa.", 422)
    return state, assignees, labels


def create_tasks_locked(project, actor, items, *, source="MANUAL", task_ids=None):
    items = list(items)
    ids = task_ids if task_ids is not None else [uuid4() for _ in items]
    facts = load_link_facts(project, items)
    prepared = [
        (task_id, dict(item), validate_links(project, item, facts=facts))
        for task_id, item in zip(ids, items, strict=True)
    ]
    sequences = allocate_sequences(project, len(prepared))
    ranks = {
        row["state_id"]: row["rank"] or 0
        for row in Task.objects.filter(
            project=project,
            state_id__in={links[0].pk for _, _, links in prepared},
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )
        .values("state_id")
        .annotate(rank=Max("sort_order"))
    }
    tasks, assignments, task_labels = [], [], []
    for sequence, (task_id, payload, (state, assignees, labels)) in zip(
        sequences, prepared, strict=True
    ):
        payload.pop("assignee_ids", None)
        payload.pop("label_ids", None)
        payload.pop("state_id", None)
        html, text, _ = clean_content(payload.pop("description_html", ""))
        ranks[state.pk] = ranks.get(state.pk, 0) + 10000
        task = Task(
            id=task_id,
            project=project,
            sequence_id=sequence,
            state=state,
            source=source,
            description_html=html,
            description_stripped=text,
            sort_order=ranks[state.pk],
            created_by_user_id=actor.id,
            completed_at=timezone.now() if state.group == "COMPLETED" else None,
            **payload,
        )
        tasks.append(task)
        assignments.extend(
            TaskAssignment(task=task, user_id=user_id) for user_id in sorted(assignees)
        )
        task_labels.extend(TaskLabel(task=task, label_id=label_id) for label_id in sorted(labels))
    Task.objects.bulk_create(tasks)
    TaskAssignment.objects.bulk_create(assignments)
    TaskLabel.objects.bulk_create(task_labels)
    loaded = task_queryset().filter(pk__in=[task.pk for task in tasks]).in_bulk()
    data = {task.pk: serialize_tasks(loaded[task.pk], many=False) for task in tasks}
    record_activities(
        [
            {"subject": task, "actor_id": actor.id, "verb": "created", "new": data[task.pk]}
            for task in tasks
        ]
    )
    emit_events(
        project,
        [
            {
                "event_type": "task.created",
                "data": data[task.pk],
                "aggregate_type": "task",
                "aggregate_id": task.pk,
                "entity_version": task.version,
            }
            for task in tasks
        ],
    )
    project.board_revision += 1
    project.save(update_fields=["board_revision"])
    return tasks


def create_task(actor, project_id, payload, scope):
    with transaction.atomic():
        project = lock_project(project_id)
        require_task_writer(project, actor, leader_only=True)
        receipt, fresh = claim_receipt(scope, payload, status=201)
        if not fresh:
            return replay_response(receipt)
        task = create_tasks_locked(project, actor, [payload])[0]
        return save_receipt(
            scope,
            payload,
            serialize_tasks(task_queryset().get(pk=task.pk), many=False),
            status=201,
            message="Đã tạo công việc.",
        )
