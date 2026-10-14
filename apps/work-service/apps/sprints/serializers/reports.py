from rest_framework import serializers


class ScopeTotalsSerializer(serializers.Serializer):
    task_count = serializers.IntegerField()
    work_item_count = serializers.IntegerField()
    completed_task_count = serializers.IntegerField()
    completed_work_item_count = serializers.IntegerField()
    cancelled_task_count = serializers.IntegerField()
    cancelled_work_item_count = serializers.IntegerField()
    blocked_task_count = serializers.IntegerField()
    overdue_task_count = serializers.IntegerField()
    estimated_count = serializers.IntegerField()
    unestimated_count = serializers.IntegerField()
    known_estimate_points = serializers.IntegerField()
    completed_estimate_points = serializers.IntegerField()
    cancelled_estimate_points = serializers.IntegerField()
    completion_percent = serializers.DecimalField(
        max_digits=7, decimal_places=2, coerce_to_string=False, allow_null=True
    )


class ProgressSerializer(serializers.Serializer):
    sprint_id = serializers.UUIDField()
    formula_version = serializers.CharField()
    captured_at = serializers.DateTimeField()
    snapshot_version = serializers.IntegerField(allow_null=True)
    totals = ScopeTotalsSerializer()


class DaySerializer(serializers.Serializer):
    date = serializers.DateField()
    observed_at = serializers.DateTimeField()
    scope_work_item_count = serializers.IntegerField()
    remaining_work_item_count = serializers.IntegerField()
    remaining_estimate_points = serializers.IntegerField()
    unestimated_remaining_count = serializers.IntegerField()


class BurndownSerializer(serializers.Serializer):
    sprint_id = serializers.UUIDField()
    formula_version = serializers.CharField()
    captured_at = serializers.DateTimeField()
    snapshot_version = serializers.IntegerField(allow_null=True)
    days = DaySerializer(many=True)
    window_truncated = serializers.BooleanField()
