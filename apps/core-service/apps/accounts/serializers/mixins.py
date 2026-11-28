"""Strict serializer input mixin compatible with Serializer, ModelSerializer, and dj-rest-auth."""

from rest_framework import serializers


class StrictInputMixin:
    """Reject unknown input fields rather than silently dropping privileged data."""

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            return super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {name: "Trường này không được phép gửi." for name in sorted(unknown)}
            )
        return super().to_internal_value(data)
