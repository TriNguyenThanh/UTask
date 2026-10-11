from rest_framework import serializers


class APIErrorSerializer(serializers.Serializer):
    """Shared error payload, preserving existing detail objects and array semantics."""

    code = serializers.CharField()
    details = serializers.ListField(child=serializers.DictField())


class ResponseEnvelopeSerializer(serializers.Serializer):
    """One response contract used by runtime rendering and schema generation."""

    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField(allow_null=True)
    meta = serializers.DictField(allow_null=True)
    error = APIErrorSerializer(allow_null=True)


class StrictInputMixin:
    """Reject unknown input fields rather than silently dropping privileged data."""

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            return super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({name: "Unknown field." for name in sorted(unknown)})
        return super().to_internal_value(data)
