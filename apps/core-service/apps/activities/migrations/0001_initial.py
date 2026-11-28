"""Initial schema for unified ClassroomActivity and WorkActivity tables (Tier 3 leaf app)."""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("collaboration", "0001_initial"),
        ("courses", "0001_initial"),
        ("projects", "0001_initial"),
        ("sprints", "0001_initial"),
        ("tasks", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomActivity",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("actor_user_id", models.UUIDField(null=True)),
                ("verb", models.CharField(max_length=100)),
                ("subject_type", models.CharField(max_length=100)),
                ("subject_id", models.UUIDField()),
                ("changes", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="courses.classsection",
                    ),
                ),
            ],
            options={
                "db_table": "classroom_activities",
                "indexes": [
                    models.Index(
                        fields=["class_section", "created_at", "id"],
                        name="ix_cls_activities_class_time",
                    ),
                    models.Index(
                        fields=["subject_type", "subject_id", "created_at"],
                        name="ix_cls_activities_subject",
                    ),
                    models.Index(
                        fields=["class_section", "verb", "created_at", "id"],
                        name="ix_cls_activities_class_verb",
                    ),
                    models.Index(
                        condition=models.Q(("actor_user_id__isnull", False)),
                        fields=["class_section", "actor_user_id", "created_at", "id"],
                        name="ix_cls_activities_class_actor",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkActivity",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("actor_user_id", models.UUIDField(null=True)),
                ("verb", models.CharField(max_length=100)),
                ("field", models.CharField(max_length=100, null=True)),
                ("old_value", models.TextField(null=True)),
                ("new_value", models.TextField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "comment",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="collaboration.comment",
                    ),
                ),
                (
                    "epic",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="tasks.epic",
                    ),
                ),
                (
                    "label",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="tasks.label",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="projects.project",
                    ),
                ),
                (
                    "project_member",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="projects.projectmember",
                    ),
                ),
                (
                    "scope_project",
                    models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scoped_activities",
                        to="projects.project",
                    ),
                ),
                (
                    "sprint",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="sprints.sprint",
                    ),
                ),
                (
                    "state",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="projects.state",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="tasks.task",
                    ),
                ),
            ],
            options={
                "db_table": "work_activities",
                "indexes": [
                    models.Index(
                        fields=["scope_project", "-created_at", "-id"],
                        name="ix_work_act_scope_proj_time",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", False),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", False),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", False),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", False),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", False),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", False),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", False),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", True),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            models.Q(
                                ("comment__isnull", True),
                                ("epic__isnull", True),
                                ("label__isnull", True),
                                ("project__isnull", True),
                                ("project_member__isnull", True),
                                ("sprint__isnull", False),
                                ("state__isnull", True),
                                ("task__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="chk_work_activity_subject",
                    ),
                ],
            },
        ),
    ]
