import django_filters
from django.apps import apps
from django.db.models import Exists, OuterRef

from apps.tasks.models import Task, TaskAssignment
from common.errors import WorkError


class BoardTaskFilter(django_filters.FilterSet):
    assignee_id = django_filters.UUIDFilter(method="filter_assignee")
    sprint_id = django_filters.CharFilter(method="filter_sprint")
    priority = django_filters.ChoiceFilter(choices=Task.Priority.choices)
    is_blocked = django_filters.BooleanFilter()

    class Meta:
        model = Task
        fields = ["assignee_id", "sprint_id", "priority", "is_blocked"]

    def filter_assignee(self, queryset, name, value):
        assignments = TaskAssignment.objects.filter(task_id=OuterRef("pk"), user_id=value)
        return queryset.annotate(_has_assignee=Exists(assignments)).filter(_has_assignee=True)

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
