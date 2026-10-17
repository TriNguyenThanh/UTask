from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    field = serializers.CharField(required=False)
    issue = serializers.CharField()


class APIErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    details = ErrorDetailSerializer(many=True)


class PaginationSerializer(serializers.Serializer):
    total_count = serializers.IntegerField(min_value=0)
    page_size = serializers.IntegerField(min_value=1)
    next_cursor = serializers.CharField(allow_null=True)
    prev_cursor = serializers.CharField(allow_null=True)
    has_next = serializers.BooleanField()


class ListMetaSerializer(serializers.Serializer):
    pagination = PaginationSerializer()


class ResponseEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField(allow_null=True)
    meta = serializers.DictField(allow_null=True)
    error = APIErrorSerializer(allow_null=True)


class StrictInputSerializer(serializers.Serializer):
    default_error_messages = {"invalid": "Dữ liệu phải là đối tượng gồm các trường thông tin."}

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {key: "Trường không được phép." for key in sorted(unknown)}
                )
        return super().to_internal_value(data)
