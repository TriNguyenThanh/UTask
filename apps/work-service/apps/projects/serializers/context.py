from rest_framework import serializers


class ContextRecordSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[
            "project",
            "task",
            "member",
            "assignment",
            "state",
            "epic",
            "label",
            "task_label",
            "relation",
            "sprint",
            "sprint_task",
            "github_link",
            "metrics",
        ]
    )
    data = serializers.DictField()


class ContextChunkSerializer(serializers.Serializer):
    chunk_index = serializers.IntegerField(min_value=0)
    records = ContextRecordSerializer(many=True)


class ContextSnapshotSerializer(serializers.Serializer):
    snapshot_id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    source_version = serializers.IntegerField(min_value=0)
    project_version = serializers.IntegerField(min_value=1)
    board_revision = serializers.IntegerField(min_value=0)
    captured_at = serializers.DateTimeField()
    sections = serializers.ListField(child=serializers.CharField())
    chunk_count = serializers.IntegerField(min_value=1)
    record_count = serializers.IntegerField(min_value=1)
    checksum = serializers.RegexField(r"^[a-f0-9]{64}$")
    chunks = ContextChunkSerializer(many=True)
