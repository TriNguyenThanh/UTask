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
    is_recruiting = models.BooleanField(default=False)
    recruitment_note = models.TextField(blank=True, default="")
    needed_skills = models.JSONField(default=list, blank=True)
    invite_code_hash = models.CharField(max_length=64, null=True)
    invite_expires_at = models.DateTimeField(null=True)
    source_version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "study_groups"
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
            ),
            models.Index(
                fields=["class_section", "status", "created_at", "id"],
                name="ix_study_groups_class_status",
            ),
            models.Index(
                fields=["class_section", "status", "is_recruiting", "created_at", "id"],
                name="ix_study_groups_recruiting",
            ),
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
    skills = models.JSONField(default=list, blank=True)
    responsibility = models.CharField(max_length=200, blank=True, default="")
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "group_members"
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
        db_table = "group_project_links"
        constraints = [
            models.UniqueConstraint(fields=["project_id"], name="uq_group_project_project")
        ]
        indexes = [
            models.Index(
                fields=["class_section", "group", "linked_at", "id"],
                name="ix_group_project_class_group",
            )
        ]


class GroupJoinRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey(
        "courses.ClassSection", on_delete=models.PROTECT, related_name="join_requests"
    )
    group = models.ForeignKey(StudyGroup, on_delete=models.PROTECT, related_name="join_requests")
    enrollment = models.ForeignKey(
        "courses.Enrollment", on_delete=models.PROTECT, related_name="join_requests"
    )
    user_id = models.UUIDField()
    status = models.CharField(max_length=20, default="PENDING")
    message = models.CharField(max_length=500, blank=True, default="")
    review_note = models.CharField(max_length=500, blank=True, default="")
    reviewed_by_user_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "group_join_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["class_section", "enrollment"],
                condition=Q(status="PENDING"),
                name="uq_pending_join_request_per_enrollment",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "APPROVED", "REJECTED", "CANCELLED"])
                & (
                    Q(status="PENDING", reviewed_at__isnull=True, reviewed_by_user_id__isnull=True)
                    | Q(
                        status__in=["APPROVED", "REJECTED"],
                        reviewed_at__isnull=False,
                        reviewed_by_user_id__isnull=False,
                    )
                    | Q(status="CANCELLED")
                ),
                name="chk_join_request_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["class_section", "group"],
                name="ix_join_req_class_group",
            ),
            models.Index(
                fields=["group", "status", "created_at", "id"],
                name="ix_join_req_group_status",
            ),
            models.Index(
                fields=["class_section", "enrollment", "created_at", "id"],
                name="ix_join_req_class_enroll",
            ),
            models.Index(
                fields=["class_section", "status"],
                condition=Q(status="PENDING"),
                name="ix_join_req_class_pending",
            ),
        ]


class GroupTopicProposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    class_section = models.ForeignKey(
        "courses.ClassSection", on_delete=models.PROTECT, related_name="topic_proposals"
    )
    group = models.OneToOneField(
        StudyGroup, on_delete=models.PROTECT, related_name="topic_proposal"
    )
    title = models.CharField(max_length=200)
    summary = models.TextField()
    objectives = models.TextField(blank=True, default="")
    status = models.CharField(max_length=30, default="DRAFT")
    teacher_feedback = models.TextField(blank=True, default="")
    submitted_by_user_id = models.UUIDField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by_user_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "group_topic_proposals"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["DRAFT", "PENDING", "APPROVED", "REVISION_REQUESTED", "REJECTED"]
                )
                & Q(version__gte=1),
                name="chk_topic_proposal_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["class_section", "group"],
                name="ix_topic_proposal_class_group",
            ),
            models.Index(
                fields=["class_section", "status", "updated_at", "id"],
                name="ix_topic_proposal_class_status",
            ),
        ]
