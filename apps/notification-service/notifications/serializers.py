"""Validation and representation of notification preferences."""

from rest_framework import serializers

from notifications.models import Preference


class PreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Preference
        fields = ["assignment", "deadline", "mention", "feedback"]

    def to_internal_value(self, data):
        if (
            not isinstance(data, dict)
            or set(data) - set(self.fields)
            or any(type(v) is not bool for v in data.values())
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Mỗi tùy chọn phải là true hoặc false."]}
            )
        return super().to_internal_value(data)
