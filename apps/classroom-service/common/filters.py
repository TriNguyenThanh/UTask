from common.errors import ClassroomError
from common.exception_handler import format_validation_issue


def apply_filterset(filterset_cls, params, queryset):
    """Apply a django-filter FilterSet and return (queryset, normalized_scope)."""
    filterset = filterset_cls(data=params, queryset=queryset)
    if not filterset.is_valid():
        details = [
            {"field": field, "issue": format_validation_issue(message)}
            for field, messages in filterset.errors.items()
            for message in messages
        ]
        raise ClassroomError(
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
