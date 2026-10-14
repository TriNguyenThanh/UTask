from rest_framework import serializers

from apps.tasks.serializers.ai import ApplyResultSerializer


class DeadlineReminderEventSerializer(serializers.Serializer):
    task_id = serializers.UUIDField()
    due_date = serializers.DateField()
    deadline_revision = serializers.CharField()
    reminder_window = serializers.DateField()
    recipient_ids = serializers.ListField(child=serializers.UUIDField())
    intent_id = serializers.RegexField(r"^[0-9a-f]{64}$")


class AIProposalAppliedEventSerializer(ApplyResultSerializer):
    actor_user_id = serializers.UUIDField()
    item_id = serializers.CharField(required=False)
    approved_payload_hash = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
    source = serializers.ChoiceField(choices=["AI_BACKLOG", "AI_DECOMPOSED", "AI_ACTION"])
