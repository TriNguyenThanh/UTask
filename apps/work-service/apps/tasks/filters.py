from uuid import UUID

import django_filters
from django.apps import apps
from django.db.models import Exists, OuterRef, Q

from apps.tasks.models import Task, TaskAssignment, TaskLabel
from common.errors import WorkError


class TaskFilter(django_filters.FilterSet):
    state_id = django_filters.UUIDFilter(
        error_messages={"invalid": "Mã trạng thái phải là UUID hợp lệ."}
    )
    epic_id = django_filters.UUIDFilter(
        error_messages={"invalid": "Mã mục tiêu lớn phải là UUID hợp lệ."}
    )
    parent_id = django_filters.UUIDFilter(
        error_messages={"invalid": "Mã công việc cha phải là UUID hợp lệ."}
    )
    type = django_filters.ChoiceFilter(
        choices=Task.Type.choices, error_messages={"invalid_choice": "Loại công việc không hợp lệ."}
    )
    priority = django_filters.ChoiceFilter(
        choices=Task.Priority.choices,
        error_messages={"invalid_choice": "Mức ưu tiên không hợp lệ."},
    )
    is_blocked = django_filters.TypedChoiceFilter(
        choices=[(value, value) for value in ["true", "false", "True", "False"]],
        coerce=lambda value: value.lower() == "true",
        error_messages={"invalid_choice": "Trạng thái chặn phải là true hoặc false."},
    )
    due_date_from = django_filters.DateFilter(
        field_name="due_date",
        lookup_expr="gte",
        error_messages={"invalid": "Ngày bắt đầu lọc phải là ngày hợp lệ."},
    )
    due_date_to = django_filters.DateFilter(
        field_name="due_date",
        lookup_expr="lte",
        error_messages={"invalid": "Ngày kết thúc lọc phải là ngày hợp lệ."},
    )
    assignee_id = django_filters.UUIDFilter(
        method="assignee", error_messages={"invalid": "Mã người phụ trách phải là UUID hợp lệ."}
    )
    label_id = django_filters.UUIDFilter(
        method="label", error_messages={"invalid": "Mã nhãn phải là UUID hợp lệ."}
    )
    search = django_filters.CharFilter(method="search_tasks")
    sprint_id = django_filters.CharFilter(method="sprint")

    def assignee(self, rows, name, value):
        return rows.filter(
            Exists(TaskAssignment.objects.filter(task_id=OuterRef("pk"), user_id=value))
        )

    def label(self, rows, name, value):
        return rows.filter(
            Exists(
                TaskLabel.objects.filter(
                    task_id=OuterRef("pk"), label_id=value, label__deleted_at__isnull=True
                )
            )
        )

    def search_tasks(self, rows, name, value):
        condition = Q(title__icontains=value) | Q(description_stripped__icontains=value)
        prefix, _, sequence = value.rpartition("-")
        if sequence.isdigit() and prefix:
            condition |= Q(project__identifier__iexact=prefix, sequence_id=int(sequence))
        return rows.filter(condition)

    def sprint(self, rows, name, value):
        if not apps.is_installed("apps.sprints"):
            if value == "none":
                return rows
            raise WorkError(
                "SPRINT_COMMAND_UNAVAILABLE", "Tính năng chu kỳ làm việc hiện chưa khả dụng.", 503
            )
        memberships = apps.get_model("sprints", "SprintTask").objects.filter(
            task_id=OuterRef("pk"), ended_at__isnull=True, deleted_at__isnull=True
        )
        if value == "none":
            return rows.filter(~Exists(memberships))
        try:
            sprint_id = UUID(value)
        except ValueError as exc:
            raise WorkError("VALIDATION_ERROR", "Mã chu kỳ làm việc không hợp lệ.") from exc
        return rows.filter(Exists(memberships.filter(sprint_id=sprint_id)))

    class Meta:
        model = Task
        fields = []
