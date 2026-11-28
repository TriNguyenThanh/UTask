import django_filters
from django.db.models import Exists, OuterRef, Q

from apps.courses.models import ClassSection, Course, Enrollment
from apps.groups.models import GroupMember
from common.errors import CoreAPIError
from common.exception_handler import format_validation_issue

ARCHIVED_CHOICES = (("true", "true"), ("false", "false"), ("all", "all"))
BOOLEAN_CHOICES = (("true", "true"), ("false", "false"))
CLASS_STATUS_CHOICES = (("OPEN", "OPEN"), ("CLOSED", "CLOSED"), ("ARCHIVED", "ARCHIVED"))
GROUPING_PHASE_CHOICES = (("FORMING", "FORMING"), ("LOCKED", "LOCKED"))
ENROLLMENT_STATUS_CHOICES = (("ACTIVE", "ACTIVE"), ("LEFT", "LEFT"), ("REMOVED", "REMOVED"))


def list_status(params, choices):
    status = params.get("status")
    if status is not None and status not in choices:
        raise CoreAPIError("VALIDATION_ERROR", "Trạng thái lọc không hợp lệ.")
    return status


def apply_filterset(filterset_cls, params, queryset):
    """Apply a django-filter FilterSet and return (queryset, normalized_scope)."""
    filterset = filterset_cls(data=params, queryset=queryset)
    if not filterset.is_valid():
        details = [
            {"field": field, "issue": format_validation_issue(message)}
            for field, messages in filterset.errors.items()
            for message in messages
        ]
        raise CoreAPIError(
            "VALIDATION_ERROR",
            "Tham số lọc không hợp lệ. Vui lòng kiểm tra lại giá trị.",
            400,
            details=details,
        )
    scope = {}
    for name in filterset.filters:
        value = filterset.form.cleaned_data.get(name)
        if value not in (None, ""):
            scope[name] = value.isoformat() if hasattr(value, "isoformat") else str(value)
    if not scope:
        return queryset, {}
    return filterset.qs, scope


class CourseFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    archived = django_filters.ChoiceFilter(choices=ARCHIVED_CHOICES, method="filter_archived")

    class Meta:
        model = Course
        fields = ["search", "archived"]

    def filter_search(self, queryset, name, value):
        query = value.strip()
        if not query:
            return queryset
        return queryset.filter(Q(code__icontains=query) | Q(name__icontains=query))

    def filter_archived(self, queryset, name, value):
        if value == "true":
            return queryset.filter(archived_at__isnull=False)
        if value == "false":
            return queryset.filter(archived_at__isnull=True)
        return queryset


class ClassSectionFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    course_id = django_filters.UUIDFilter(field_name="course_id")
    term = django_filters.CharFilter(field_name="term", lookup_expr="iexact")
    status = django_filters.ChoiceFilter(choices=CLASS_STATUS_CHOICES)
    grouping_phase = django_filters.ChoiceFilter(choices=GROUPING_PHASE_CHOICES)

    class Meta:
        model = ClassSection
        fields = ["search", "course_id", "term", "status", "grouping_phase"]

    def filter_search(self, queryset, name, value):
        query = value.strip()
        if not query:
            return queryset
        return queryset.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(term__icontains=query)
            | Q(course__code__icontains=query)
            | Q(course__name__icontains=query)
        )


class EnrollmentFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ENROLLMENT_STATUS_CHOICES)
    has_group = django_filters.ChoiceFilter(choices=BOOLEAN_CHOICES, method="filter_has_group")
    user_id = django_filters.UUIDFilter(field_name="user_id")

    class Meta:
        model = Enrollment
        fields = ["status", "has_group", "user_id"]

    def filter_has_group(self, queryset, name, value):
        active_group = GroupMember.objects.filter(
            enrollment_id=OuterRef("pk"),
            status="ACTIVE",
            group__status="ACTIVE",
        )
        qs = queryset.annotate(_has_active_group=Exists(active_group))
        return qs.filter(_has_active_group=(value == "true"))
