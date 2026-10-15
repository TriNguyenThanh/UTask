from rest_framework import serializers


class MetricTotalsSerializer(serializers.Serializer):
    task_count = serializers.IntegerField()
    work_item_count = serializers.IntegerField()
    completed_task_count = serializers.IntegerField()
    completed_work_item_count = serializers.IntegerField()
    cancelled_task_count = serializers.IntegerField()
    cancelled_work_item_count = serializers.IntegerField()
    blocked_task_count = serializers.IntegerField()
    dependency_blocked_task_count = serializers.IntegerField()
    overdue_task_count = serializers.IntegerField()
    estimated_count = serializers.IntegerField()
    unestimated_count = serializers.IntegerField()
    known_estimate_points = serializers.IntegerField()
    completed_estimate_points = serializers.IntegerField()
    cancelled_estimate_points = serializers.IntegerField()
    completion_percent = serializers.DecimalField(
        max_digits=7, decimal_places=2, allow_null=True, coerce_to_string=False
    )


class StateDistributionSerializer(serializers.Serializer):
    group = serializers.CharField()
    task_count = serializers.IntegerField()
    work_item_count = serializers.IntegerField()


class AssigneeDistributionSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    status = serializers.CharField(allow_null=True)
    weekly_capacity = serializers.IntegerField(allow_null=True)
    assigned_work_item_count = serializers.IntegerField()
    unestimated_work_item_count = serializers.IntegerField()
    allocated_estimate_points = serializers.DecimalField(
        max_digits=20, decimal_places=2, coerce_to_string=False
    )


class DashboardSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    formula_version = serializers.CharField()
    scope = serializers.ChoiceField(choices=["ACTIVE_TASKS"])
    computed_at = serializers.DateTimeField()
    business_date = serializers.DateField()
    source_event_sequence = serializers.IntegerField()
    board_revision = serializers.IntegerField()
    totals = MetricTotalsSerializer()
    state_distribution = StateDistributionSerializer(many=True)
    assignee_distribution = AssigneeDistributionSerializer(many=True)
    unassigned_estimate_points = serializers.IntegerField()
