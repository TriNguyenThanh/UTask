from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.messaging.models import IdempotencyRecord, OutboxEvent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


def test_migrations_reverse_forward_and_exact_ten_business_tables():
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    executor.migrate([("groups", None), ("messaging", None), ("courses", None)])
    assert "GROUP_MEMBERS" not in connection.introspection.table_names()
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    assert set(connection.introspection.table_names()) - {
        "django_migrations",
        "django_content_type",
    } == {
        "COURSES",
        "CLASS_SECTIONS",
        "CLASS_TEACHERS",
        "ENROLLMENTS",
        "STUDY_GROUPS",
        "GROUP_MEMBERS",
        "GROUP_PROJECT_LINKS",
        "ACTIVITIES",
        "OUTBOX_EVENTS",
        "IDEMPOTENCY_RECORDS",
    }


@pytest.mark.parametrize("kind", ["group", "enrollment", "project"])
def test_database_rejects_cross_class_relationship_even_direct_sql(section, actors, kind):
    other = ClassSection.objects.create(
        course=section.course,
        code="OTHER",
        name="Lớp khác",
        term="2026",
        starts_on=section.starts_on,
        ends_on=section.ends_on,
    )
    group = StudyGroup.objects.create(
        class_section=other if kind in {"group", "project"} else section, name="Nhóm"
    )
    enrollment = Enrollment.objects.create(
        class_section=other if kind == "enrollment" else section, user_id=uuid4()
    )
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        if kind == "project":
            cursor.execute(
                'INSERT INTO "GROUP_PROJECT_LINKS" '
                "(id,class_section_id,group_id,project_id,linked_at) VALUES (%s,%s,%s,%s,%s)",
                [uuid4(), section.pk, group.pk, uuid4(), timezone.now()],
            )
        else:
            cursor.execute(
                'INSERT INTO "GROUP_MEMBERS" '
                "(id,class_section_id,group_id,enrollment_id,role,status,joined_at,left_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)",
                [uuid4(), section.pk, group.pk, enrollment.pk, "MEMBER", "ACTIVE", timezone.now()],
            )
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_each_foreign_key_has_a_covering_unconditional_index():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.conrelid::regclass::text, c.conname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE c.contype = 'f' AND n.nspname = 'public'
              AND NOT EXISTS (
                  SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid
                  AND i.indisvalid AND i.indpred IS NULL
                  AND (i.indkey::smallint[])[0:cardinality(c.conkey)-1] @> c.conkey
              )
        """)
        assert cursor.fetchall() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "UNKNOWN"),
        ("grouping_phase", "LOCKED"),
        ("version", 0),
        ("group_min_size", 0),
        ("group_max_size", 0),
        ("starts_on", "2027-01-01"),
    ],
)
def test_class_check_constraints_reject_invalid_state(section, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        ClassSection.objects.filter(pk=section.pk).update(**{field: value})


def test_partial_uniques_keep_one_leader_one_group_but_multiple_history(group, actors):
    section = group.class_section
    outsider = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    with pytest.raises(IntegrityError), transaction.atomic():
        GroupMember.objects.create(
            class_section=section, group=group, enrollment=outsider, role="LEADER"
        )
    existing = GroupMember.objects.get(group=group, role="MEMBER")
    with pytest.raises(IntegrityError), transaction.atomic():
        GroupMember.objects.create(
            class_section=section, group=group, enrollment=existing.enrollment
        )
    existing.status, existing.left_at = "LEFT", timezone.now()
    existing.save()
    GroupMember.objects.create(class_section=section, group=group, enrollment=existing.enrollment)
    assert GroupMember.objects.filter(enrollment=existing.enrollment).count() == 2


@pytest.mark.parametrize(
    "model,values",
    [
        (ClassTeacher, {"user_id": uuid4(), "status": "LEFT"}),
        (Enrollment, {"user_id": uuid4(), "source": "INVALID"}),
        (StudyGroup, {"name": "Sai", "source_version": 0}),
        (
            OutboxEvent,
            {
                "class_sequence": 0,
                "aggregate_type": "group",
                "aggregate_id": uuid4(),
                "event_type": "changed",
                "data": {},
            },
        ),
        (
            IdempotencyRecord,
            {
                "actor_user_id": uuid4(),
                "http_method": "POST",
                "endpoint_path": "/test/",
                "idempotency_key": uuid4(),
                "payload_hash": "a" * 64,
                "status": "COMPLETED",
                "expires_at": timezone.now() + timedelta(hours=1),
            },
        ),
    ],
)
def test_all_domain_state_constraints_are_enforced(section, model, values):
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(class_section=section, **values)


def test_project_unique_allows_multiple_projects_for_same_group(group):
    first = uuid4()
    GroupProjectLink.objects.create(
        class_section=group.class_section, group=group, project_id=first
    )
    GroupProjectLink.objects.create(
        class_section=group.class_section, group=group, project_id=uuid4()
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        GroupProjectLink.objects.create(
            class_section=group.class_section, group=group, project_id=first
        )
    assert GroupProjectLink.objects.count() == 2
