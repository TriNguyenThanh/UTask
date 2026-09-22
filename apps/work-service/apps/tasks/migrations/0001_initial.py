import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("projects", "0001_initial"), ("sprints", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TODO", "Todo"),
                            ("IN_PROGRESS", "In Progress"),
                            ("REVIEW", "Review"),
                            ("DONE", "Done"),
                        ],
                        default="TODO",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
                        default="MEDIUM",
                        max_length=20,
                    ),
                ),
                ("story_points", models.PositiveIntegerField(default=0)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("depends_on", models.ManyToManyField(blank=True, to="tasks.task")),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                        to="projects.project",
                    ),
                ),
                (
                    "sprint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tasks",
                        to="sprints.sprint",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TaskAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("user_id", models.CharField(max_length=100)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="tasks.task",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="taskassignment",
            constraint=models.UniqueConstraint(
                fields=("task", "user_id"), name="unique_task_assignment"
            ),
        ),
    ]
