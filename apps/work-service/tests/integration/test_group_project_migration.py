import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]


def test_group_project_migration_preserves_identifier_and_guards_unsafe_rollback():
    previous = [("projects", "0001_initial")]
    current = [("projects", "0002_multiple_group_projects")]

    def migrate(target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps.get_model("projects", "Project")

    def constraints():
        with connection.cursor() as cursor:
            return connection.introspection.get_constraints(cursor, "projects")

    try:
        project_model = migrate(previous)
        assert constraints()["uq_one_primary_project_per_group"]["unique"]
        assert "ix_project_active_group" not in constraints()
        first = project_model.objects.create(
            identifier="FIRST", name="Dự án thứ nhất", classroom_group_id="migration-group"
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            project_model.objects.create(
                identifier="SECOND", name="Dự án thứ hai", classroom_group_id="migration-group"
            )

        project_model = migrate(current)
        actual = constraints()
        assert "uq_one_primary_project_per_group" not in actual
        assert actual["ix_project_active_group"]["index"]
        assert actual["uq_projects_identifier"]["unique"]
        second = project_model.objects.create(
            identifier="SECOND", name="Dự án thứ hai", classroom_group_id="migration-group"
        )
        assert project_model.objects.filter(classroom_group_id="migration-group").count() == 2
        with pytest.raises(IntegrityError), transaction.atomic():
            project_model.objects.create(
                identifier=first.identifier, name="Trùng mã dự án", classroom_group_id="other"
            )
        # Rolling back cannot silently discard projects now allowed by the migration.
        with pytest.raises(IntegrityError):
            migrate(previous)
        assert project_model.objects.filter(classroom_group_id="migration-group").count() == 2
        second.delete()
        migrate(previous)
        assert constraints()["uq_one_primary_project_per_group"]["unique"]
    finally:
        migrate(current)
