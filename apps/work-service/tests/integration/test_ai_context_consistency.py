from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.projects.models import ProjectMember
from apps.projects.queries.ai_context import read_ai_context
from apps.projects.services.locking import lock_project
from common.authentication import Actor

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


@pytest.mark.parametrize("revoke", [False, True])
def test_context_waits_for_writer_barrier_then_observes_committed_version_or_revocation(
    created_project, actors, revoke
):
    ready, release, attempting = Event(), Event(), Event()
    project_id = UUID(created_project["id"])

    def writer():
        close_old_connections()
        try:
            with transaction.atomic():
                project = lock_project(project_id)
                project.name = "Tên và phiên bản đã commit"
                project.event_sequence += 1
                project.save(update_fields=["name", "event_sequence"])
                if revoke:
                    ProjectMember.objects.filter(project=project, user_id=actors["member"]).update(
                        status="REMOVED", left_at=timezone.now()
                    )
                ready.set()
                assert release.wait(5)
                return project.event_sequence
        finally:
            connection.close()

    def reader():
        close_old_connections()
        try:
            attempting.set()
            return read_ai_context(Actor(actors["member"]), "project", project_id, "project")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(writer)
        assert ready.wait(5)
        reading = pool.submit(reader)
        assert attempting.wait(5)
        try:
            # Confirm a second PostgreSQL backend really blocks on the writer lock.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE datname=current_database() AND wait_event_type='Lock')"
                )
                blocked = cursor.fetchone()[0]
            if not blocked:
                for _ in range(100):
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE datname=current_database() AND wait_event_type='Lock')"
                        )
                        if cursor.fetchone()[0]:
                            blocked = True
                            break
            assert blocked, "Reader did not reach the PostgreSQL Project barrier"
        finally:
            release.set()
        version = writing.result(timeout=5)
        if revoke:
            with pytest.raises(NotFound):
                reading.result(timeout=5)
        else:
            document = reading.result(timeout=5)
            assert document["data"]["name"] == "Tên và phiên bản đã commit"
            assert document["source_version"] == str(version)
