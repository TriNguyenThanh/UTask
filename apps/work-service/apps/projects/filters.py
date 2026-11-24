import django_filters
from django.apps import apps
from django.db.models import Exists, OuterRef, Q

from apps.tasks.models import Task, TaskAssignment, TaskLabel
from common.errors import WorkError


class BoardTaskFilter(django_filters.FilterSet):
    assignee_id = django_filters.UUIDFilter(method="filter_assignee")
    sprint_id = django_filters.CharFilter(method="filter_sprint")
    priority = django_filters.ChoiceFilter(choices=Task.Priority.choices)
    is_blocked = django_filters.BooleanFilter()
    epic_id = django_filters.UUIDFilter()
    label_id = django_filters.UUIDFilter(method="filter_label")
    type = django_filters.ChoiceFilter(choices=Task.Type.choices)
    search = django_filters.CharFilter(method="filter_search")
    include_subtasks = django_filters.BooleanFilter(method="filter_include_subtasks")

    class Meta:
        model = Task
        fields = [
            "assignee_id",
            "sprint_id",
            "priority",
            "is_blocked",
            "epic_id",
            "label_id",
            "type",
            "search",
            "include_subtasks",
        ]

    def filter_assignee(self, queryset, name, value):
        assignments = TaskAssignment.objects.filter(task_id=OuterRef("pk"), user_id=value)
        return queryset.annotate(_has_assignee=Exists(assignments)).filter(_has_assignee=True)

    def filter_label(self, queryset, name, value):
        labels = TaskLabel.objects.filter(
            task_id=OuterRef("pk"), label_id=value, label__deleted_at__isnull=True
        )
        return queryset.annotate(_has_label=Exists(labels)).filter(_has_label=True)

    def filter_search(self, queryset, name, value):
        condition = Q(title__icontains=value) | Q(description_stripped__icontains=value)
        prefix, _, sequence = value.strip().rpartition("-")
        if sequence.isdigit() and prefix:
            condition |= Q(project__identifier__iexact=prefix, sequence_id=int(sequence))
        return queryset.filter(condition)

    def filter_include_subtasks(self, queryset, name, value):
        # Default-false semantics live in filtered_tasks so omitting this param hides subtasks.
        return queryset

    def filter_sprint(self, queryset, name, value):
        if not apps.is_installed("apps.sprints"):
            if value == "none":
                return queryset
            raise WorkError("INVALID_OPERATION", "Tính năng chu kỳ làm việc hiện chưa khả dụng.")
        membership = apps.get_model("sprints", "SprintTask").objects.filter(
            task_id=OuterRef("pk"), ended_at__isnull=True, deleted_at__isnull=True
        )
        if value != "none":
            membership = membership.filter(sprint_id=value)
        queryset = queryset.annotate(_in_sprint=Exists(membership))
        return queryset.filter(_in_sprint=value != "none")
