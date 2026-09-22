import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Repository",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("project_id", models.CharField(max_length=100)),
                ("github_repository_id", models.CharField(max_length=100, unique=True)),
                ("full_name", models.CharField(max_length=300)),
                ("default_branch", models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name="PullRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("number", models.PositiveIntegerField()),
                ("author_id", models.CharField(max_length=100)),
                ("state", models.CharField(max_length=20)),
                ("updated_at", models.DateTimeField()),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pull_requests",
                        to="github.repository",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Commit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("sha", models.CharField(max_length=100)),
                ("author_id", models.CharField(max_length=100)),
                ("timestamp", models.DateTimeField()),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="commits",
                        to="github.repository",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaskGitHubReference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("task_id", models.CharField(max_length=100)),
                ("reference_type", models.CharField(max_length=20)),
                ("reference_number", models.PositiveIntegerField()),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="github.repository"
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="commit",
            constraint=models.UniqueConstraint(
                fields=("repository", "sha"), name="unique_repository_commit"
            ),
        ),
        migrations.AddConstraint(
            model_name="pullrequest",
            constraint=models.UniqueConstraint(
                fields=("repository", "number"), name="unique_repository_pull_request"
            ),
        ),
    ]
