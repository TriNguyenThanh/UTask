import django_filters

from apps.groups.models import StudyGroup

GROUP_STATUS_CHOICES = (("ACTIVE", "ACTIVE"), ("ARCHIVED", "ARCHIVED"))


class StudyGroupFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    status = django_filters.ChoiceFilter(choices=GROUP_STATUS_CHOICES)

    class Meta:
        model = StudyGroup
        fields = ["search", "status"]

    def filter_search(self, queryset, name, value):
        query = value.strip()
        if not query:
            return queryset
        return queryset.filter(name__icontains=query)
