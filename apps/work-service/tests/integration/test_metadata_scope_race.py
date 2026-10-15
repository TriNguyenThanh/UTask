import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership
from infrastructure.classroom import GroupMemberFact
from tests.fixtures.transactions import effect_state

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


@pytest.mark.parametrize("kind", ["labels", "epics"])
@pytest.mark.parametrize("revocation", ["membership", "archive"])
def test_metadata_command_rechecks_scope_after_preflight_and_project_lock(
    created_project, actors, client_for, group, kind, revocation
):
    project_id = created_project["id"]
    path = f"/projects/{project_id}/{kind}/"
    payload = {"name": "Race", **({"color": "#123456"} if kind == "labels" else {})}

    def write():
        close_old_connections()
        try:
            reply = client_for(actors["leader"]).post(path, payload, format="json")
            return reply.status_code, reply.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Project.objects.select_for_update().get(pk=project_id)
            future = pool.submit(write)
            deadline = time.monotonic() + 3
            blocked = False
            while time.monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_stat_clear_snapshot()")
                    cursor.execute(
                        """SELECT EXISTS(
                          SELECT 1 FROM pg_stat_activity
                          WHERE datname=current_database() AND pid<>pg_backend_pid()
                            AND wait_event_type='Lock' AND query ILIKE %s)""",
                        ['%"projects"%'],
                    )
                    blocked = cursor.fetchone()[0]
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "Writer never reached Project command lock after preflight"
            if revocation == "membership":
                snapshot = replace(
                    group,
                    source_version=2,
                    members=(
                        GroupMemberFact(actors["leader"], "MEMBER", "LEFT"),
                        GroupMemberFact(actors["member"], "LEADER"),
                    ),
                )
                assert synchronize_membership(project_id, snapshot) is True
            else:
                Project.objects.filter(pk=project_id).update(archived_at=timezone.now())
            before = effect_state(project_id)
        status, body = future.result(timeout=10)
    assert status == (404 if revocation == "membership" else 400), body
    assert body["success"] is False and effect_state(project_id) == before
