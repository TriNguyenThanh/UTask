"""Initial schema for study_groups, group_members, group_project_links, join requests, topics."""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("courses", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudyGroup",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("status", models.CharField(default="ACTIVE", max_length=20)),
                ("is_recruiting", models.BooleanField(default=False)),
                ("recruitment_note", models.TextField(blank=True, default="")),
                ("needed_skills", models.JSONField(blank=True, default=list)),
                ("invite_code_hash", models.CharField(max_length=64, null=True)),
                ("invite_expires_at", models.DateTimeField(null=True)),
                ("source_version", models.PositiveBigIntegerField(default=1)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="groups",
                        to="courses.classsection",
                    ),
                ),
            ],
            options={
                "db_table": "study_groups",
                "indexes": [
                    models.Index(
                        fields=["class_section", "created_at", "id"],
                        name="ix_study_groups_class_list",
                    ),
                    models.Index(
                        fields=["class_section", "status", "created_at", "id"],
                        name="ix_study_groups_class_status",
                    ),
                    models.Index(
                        fields=["class_section", "status", "is_recruiting", "created_at", "id"],
                        name="ix_study_groups_recruiting",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("class_section", "id"), name="uq_study_group_class_id"
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("invite_code_hash__isnull", False)),
                        fields=("invite_code_hash",),
                        name="uq_study_groups_invite_code",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("source_version__gte", 1), ("status__in", ["ACTIVE", "ARCHIVED"])
                        ),
                        name="chk_study_group_state",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GroupMember",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("role", models.CharField(default="MEMBER", max_length=20)),
                ("status", models.CharField(default="ACTIVE", max_length=20)),
                ("skills", models.JSONField(blank=True, default=list)),
                ("responsibility", models.CharField(blank=True, default="", max_length=200)),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("left_at", models.DateTimeField(null=True)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="courses.classsection",
                    ),
                ),
                (
                    "enrollment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="memberships",
                        to="courses.enrollment",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="members",
                        to="groups.studygroup",
                    ),
                ),
            ],
            options={
                "db_table": "group_members",
                "indexes": [
                    models.Index(
                        fields=["class_section", "group"], name="ix_group_members_class_group"
                    ),
                    models.Index(
                        fields=["class_section", "enrollment"],
                        name="ix_group_members_class_enroll",
                    ),
                    models.Index(
                        fields=["class_section", "joined_at", "id"],
                        name="ix_group_members_class_history",
                    ),
                    models.Index(
                        condition=models.Q(("status", "ACTIVE")),
                        fields=["group", "role", "enrollment"],
                        name="ix_group_members_group_active",
                    ),
                    models.Index(
                        fields=["enrollment", "joined_at", "id"],
                        name="ix_group_member_enroll_history",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "ACTIVE")),
                        fields=("class_section", "enrollment"),
                        name="uq_active_group_per_enrollment",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("role", "LEADER"), ("status", "ACTIVE")),
                        fields=("group",),
                        name="uq_active_leader_per_group",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("role__in", ["LEADER", "MEMBER"]))
                        & (
                            models.Q(("left_at__isnull", True), ("status", "ACTIVE"))
                            | models.Q(
                                ("left_at__gte", models.F("joined_at")),
                                ("left_at__isnull", False),
                                ("status__in", ["LEFT", "REMOVED"]),
                            )
                        ),
                        name="chk_group_member_state",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GroupProjectLink",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("project_id", models.UUIDField()),
                ("linked_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="courses.classsection",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="project_links",
                        to="groups.studygroup",
                    ),
                ),
            ],
            options={
                "db_table": "group_project_links",
                "indexes": [
                    models.Index(
                        fields=["class_section", "group", "linked_at", "id"],
                        name="ix_group_project_class_group",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("project_id",), name="uq_group_project_project"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GroupJoinRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("user_id", models.UUIDField()),
                ("status", models.CharField(default="PENDING", max_length=20)),
                ("message", models.CharField(blank=True, default="", max_length=500)),
                ("review_note", models.CharField(blank=True, default="", max_length=500)),
                ("reviewed_by_user_id", models.UUIDField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="join_requests",
                        to="courses.classsection",
                    ),
                ),
                (
                    "enrollment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="join_requests",
                        to="courses.enrollment",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="join_requests",
                        to="groups.studygroup",
                    ),
                ),
            ],
            options={
                "db_table": "group_join_requests",
                "indexes": [
                    models.Index(fields=["class_section", "group"], name="ix_join_req_class_group"),
                    models.Index(
                        fields=["group", "status", "created_at", "id"],
                        name="ix_join_req_group_status",
                    ),
                    models.Index(
                        fields=["class_section", "enrollment", "created_at", "id"],
                        name="ix_join_req_class_enroll",
                    ),
                    models.Index(
                        condition=models.Q(("status", "PENDING")),
                        fields=["class_section", "status"],
                        name="ix_join_req_class_pending",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "PENDING")),
                        fields=("class_section", "enrollment"),
                        name="uq_pending_join_request_per_enrollment",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("status__in", ["PENDING", "APPROVED", "REJECTED", "CANCELLED"])
                        )
                        & (
                            models.Q(
                                ("reviewed_at__isnull", True),
                                ("reviewed_by_user_id__isnull", True),
                                ("status", "PENDING"),
                            )
                            | models.Q(
                                ("reviewed_at__isnull", False),
                                ("reviewed_by_user_id__isnull", False),
                                ("status__in", ["APPROVED", "REJECTED"]),
                            )
                            | models.Q(("status", "CANCELLED"))
                        ),
                        name="chk_join_request_state",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="GroupTopicProposal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("summary", models.TextField()),
                ("objectives", models.TextField(blank=True, default="")),
                ("status", models.CharField(default="DRAFT", max_length=30)),
                ("teacher_feedback", models.TextField(blank=True, default="")),
                ("submitted_by_user_id", models.UUIDField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_by_user_id", models.UUIDField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "class_section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="topic_proposals",
                        to="courses.classsection",
                    ),
                ),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="topic_proposal",
                        to="groups.studygroup",
                    ),
                ),
            ],
            options={
                "db_table": "group_topic_proposals",
                "indexes": [
                    models.Index(
                        fields=["class_section", "group"], name="ix_topic_proposal_class_group"
                    ),
                    models.Index(
                        fields=["class_section", "status", "updated_at", "id"],
                        name="ix_topic_proposal_class_status",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "status__in",
                                ["DRAFT", "PENDING", "APPROVED", "REVISION_REQUESTED", "REJECTED"],
                            )
                        )
                        & models.Q(("version__gte", 1)),
                        name="chk_topic_proposal_state",
                    ),
                ],
            },
        ),
    ]
