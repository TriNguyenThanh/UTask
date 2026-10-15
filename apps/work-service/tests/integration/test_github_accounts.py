import pytest

from apps.integrations.services.accounts import apply_account_fact
from apps.projects.models import ProjectMember
from infrastructure.integration import AccountFact

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_declared_username_is_not_proof_source_verifies_and_stale_unlink_ignored(
    created_project, actors, client_for
):
    route = f"/projects/{created_project['id']}/members/{actors['member']}/github/"
    client = client_for(actors["member"])
    assert client.patch(route, {"github_username": "student"}, format="json").status_code == 200
    member = ProjectMember.objects.get(user_id=actors["member"])
    assert not member.is_github_verified and member.github_user_id is None
    assert (
        client.patch(
            route, {"github_username": "student", "is_github_verified": True}, format="json"
        ).status_code
        == 400
    )
    verified = AccountFact(actors["member"], "provider-42", "Student", 2, True)
    assert apply_account_fact(verified) == 1
    member.refresh_from_db()
    assert member.is_github_verified and member.github_user_id == "provider-42"
    assert (
        apply_account_fact(AccountFact(actors["member"], "provider-42", "Student", 1, False)) == 0
    )
    assert apply_account_fact(AccountFact(actors["member"], "other", "Student", 3, False)) == 0
    assert (
        apply_account_fact(AccountFact(actors["member"], "provider-42", "Student", 3, False)) == 1
    )
    member.refresh_from_db()
    assert not member.is_github_verified and member.github_user_id == "provider-42"


def test_verification_notification_intent_replay_notifies_once(created_project, actors, client_for):
    from apps.messaging.models import OutboxEvent

    route = (
        f"/projects/{created_project['id']}/members/{actors['member']}/github/request-verification/"
    )
    client = client_for(actors["leader"])
    first = client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="remind")
    assert first.status_code == 200
    assert (
        client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="remind").json() == first.json()
    )
    assert (
        OutboxEvent.objects.filter(
            event_type="project.member.github_verification_requested"
        ).count()
        == 1
    )
    assert (
        client_for(actors["member"])
        .post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="member")
        .status_code
        == 403
    )
