import django_filters

from apps.activities.models import ClassroomActivity


class ClassroomActivityFilter(django_filters.FilterSet):
    verb = django_filters.CharFilter(field_name="verb", lookup_expr="exact")
    actor_user_id = django_filters.UUIDFilter(field_name="actor_user_id")
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ClassroomActivity
        fields = ["verb", "actor_user_id", "created_from", "created_to"]
