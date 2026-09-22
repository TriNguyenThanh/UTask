import uuid

from django.db import models


class Repository(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.CharField(max_length=100)
    github_repository_id = models.CharField(max_length=100, unique=True)
    full_name = models.CharField(max_length=300)
    default_branch = models.CharField(max_length=200, blank=True)


class Commit(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="commits")
    sha = models.CharField(max_length=100)
    author_id = models.CharField(max_length=100)
    timestamp = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["repository", "sha"], name="unique_repository_commit")
        ]


class PullRequest(models.Model):
    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="pull_requests"
    )
    number = models.PositiveIntegerField()
    author_id = models.CharField(max_length=100)
    state = models.CharField(max_length=20)
    updated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "number"], name="unique_repository_pull_request"
            )
        ]


class TaskGitHubReference(models.Model):
    task_id = models.CharField(max_length=100)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    reference_type = models.CharField(max_length=20)
    reference_number = models.PositiveIntegerField()
