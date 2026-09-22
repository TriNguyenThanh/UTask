import uuid

from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "TODO"
        IN_PROGRESS = "IN_PROGRESS"
        REVIEW = "REVIEW"
        DONE = "DONE"

    class Priority(models.TextChoices):
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="tasks")
    sprint = models.ForeignKey(
        "sprints.Sprint", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    story_points = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True)


class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    user_id = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "user_id"], name="unique_task_assignment")
        ]
