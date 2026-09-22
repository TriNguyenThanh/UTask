import uuid

from django.db import models


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        LEADER = "LEADER"
        MEMBER = "MEMBER"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user_id = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    weekly_capacity = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user_id"], name="unique_project_member")
        ]
