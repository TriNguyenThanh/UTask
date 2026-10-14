from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from apps.projects.services.membership import synchronize_membership
from infrastructure.classroom import GroupMemberFact
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("operation", ["confirm", "download", "delete"])
def test_missing_attachment_in_valid_subject_returns_not_found_without_effect(
    pending_file, operation
):
    leader, task, route, _ = pending_file
    before = effect_state(task["project_id"])
    missing = str(uuid4())
    reply = (
        leader.post(
            route, {"attachment_id": missing}, format="json", HTTP_IDEMPOTENCY_KEY="missing-upload"
        )
        if operation == "confirm"
        else leader.get(route + missing + "/download/")
        if operation == "download"
        else leader.delete(route + missing + "/")
    )
    assert reply.status_code == 404, reply.content
    assert effect_state(task["project_id"]) == before


def test_expired_pending_upload_rejects_before_object_inspection(
    pending_file, storage, monkeypatch
):
    leader, task, route, row = pending_file
    monkeypatch.setattr("django.utils.timezone.now", lambda: row.expires_at + timedelta(seconds=1))
    monkeypatch.setattr(
        storage, "inspect", lambda self, row: pytest.fail("Expired lease must not call storage")
    )
    before = effect_state(task["project_id"])
    reply = leader.post(
        route,
        {"attachment_id": str(row.pk)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="expired-before-inspect",
    )
    assert reply.status_code == 400, reply.content
    row.refresh_from_db()
    assert row.status == "PENDING" and row.confirmed_at is None
    assert effect_state(task["project_id"]) == before


@pytest.mark.parametrize("interleave", ["delete", "membership"])
def test_confirmation_rechecks_committed_deletion_or_membership_after_external_inspection(
    pending_file, storage, group, actors, monkeypatch, interleave
):
    leader, task, route, row = pending_file
    original = storage.inspect
    committed = {}

    def inspect(adapter, attachment):
        facts = original(adapter, attachment)
        if interleave == "delete":
            reply = leader.delete(route + str(row.pk) + "/")
            assert reply.status_code == 200, reply.content
        else:
            source = replace(
                group,
                source_version=2,
                members=(
                    GroupMemberFact(actors["leader"], "MEMBER", "LEFT"),
                    GroupMemberFact(actors["member"], "LEADER"),
                ),
            )
            assert synchronize_membership(task["project_id"], source) is True
        committed["effects"] = effect_state(task["project_id"])
        return facts

    monkeypatch.setattr(storage, "inspect", inspect)
    reply = leader.post(
        route, {"attachment_id": str(row.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="inspection-race"
    )
    assert reply.status_code == 404, reply.content
    row.refresh_from_db()
    assert row.status == "PENDING" and row.confirmed_at is None
    assert effect_state(task["project_id"]) == committed["effects"]
