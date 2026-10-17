from uuid import uuid4

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class StudyGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey(
        "courses.ClassSection", on_delete=models.PROTECT, related_name="groups"
    )
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, default="ACTIVE")
    invite_code_hash = models.CharField(max_length=64, null=True)
    invite_expires_at = models.DateTimeField(null=True)
    source_version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "STUDY_GROUPS"
        constraints = [
            models.UniqueConstraint(fields=["class_section", "id"], name="uq_study_group_class_id"),
            models.UniqueConstraint(
                fields=["invite_code_hash"],
                condition=Q(invite_code_hash__isnull=False),
                name="uq_study_groups_invite_code",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["ACTIVE", "ARCHIVED"], source_version__gte=1),
                name="chk_study_group_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["class_section", "created_at", "id"], name="ix_study_groups_class_list"
            )
        ]


class GroupMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT)
    group = models.ForeignKey(StudyGroup, on_delete=models.PROTECT, related_name="members")
    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=20, default="MEMBER")
    status = models.CharField(max_length=20, default="ACTIVE")
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "GROUP_MEMBERS"
        constraints = [
            models.UniqueConstraint(
                fields=["class_section", "enrollment"],
                condition=Q(status="ACTIVE"),
                name="uq_active_group_per_enrollment",
            ),
            models.UniqueConstraint(
                fields=["group"],
                condition=Q(status="ACTIVE", role="LEADER"),
                name="uq_active_leader_per_group",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["LEADER", "MEMBER"])
                & (
                    Q(status="ACTIVE", left_at__isnull=True)
                    | Q(
                        status__in=["LEFT", "REMOVED"],
                        left_at__isnull=False,
                        left_at__gte=F("joined_at"),
                    )
                ),
                name="chk_group_member_state",
            ),
        ]
        indexes = [
            models.Index(fields=["class_section", "group"], name="ix_group_members_class_group"),
            models.Index(
                fields=["class_section", "enrollment"], name="ix_group_members_class_enroll"
            ),
            models.Index(
                fields=["class_section", "joined_at", "id"], name="ix_group_members_class_history"
            ),
            models.Index(
                fields=["group", "role", "enrollment"],
                condition=Q(status="ACTIVE"),
                name="ix_group_members_group_active",
            ),
            models.Index(
                fields=["enrollment", "joined_at", "id"], name="ix_group_member_enroll_history"
            ),
        ]


class GroupProjectLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey("courses.ClassSection", on_delete=models.PROTECT)
    group = models.ForeignKey(StudyGroup, on_delete=models.PROTECT, related_name="project_links")
    project_id = models.UUIDField()
    linked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "GROUP_PROJECT_LINKS"
        constraints = [
            models.UniqueConstraint(fields=["project_id"], name="uq_group_project_project")
        ]
        indexes = [
            models.Index(
                fields=["class_section", "group", "linked_at", "id"],
                name="ix_group_project_class_group",
            )
        ]
