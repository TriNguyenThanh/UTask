from rest_framework import serializers

from .models import Task, TaskAssignment


class TaskSerializer(serializers.ModelSerializer):
    assignee_ids = serializers.ListField(
        child=serializers.CharField(), required=False, write_only=True
    )
    assignees = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "story_points",
            "due_date",
            "sprint",
            "assignee_ids",
            "assignees",
        ]
        read_only_fields = ["id"]

    def get_assignees(self, task):
        return list(task.assignments.values_list("user_id", flat=True))

    def _save_assignments(self, task, assignee_ids):
        if assignee_ids is not None:
            task.assignments.all().delete()
            TaskAssignment.objects.bulk_create(
                [TaskAssignment(task=task, user_id=user_id) for user_id in assignee_ids]
            )

    def create(self, validated_data):
        assignee_ids = validated_data.pop("assignee_ids", None)
        task = Task.objects.create(**validated_data)
        self._save_assignments(task, assignee_ids)
        return task

    def update(self, instance, validated_data):
        assignee_ids = validated_data.pop("assignee_ids", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        self._save_assignments(instance, assignee_ids)
        return instance
