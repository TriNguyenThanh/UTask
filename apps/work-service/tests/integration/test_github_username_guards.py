import pytest
from django.utils import timezone

from apps.integrations.services.accounts import apply_account_fact
from apps.projects.models import Project, ProjectMember
from infrastructure.integration import AccountFact
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "guard", ["other-member", "inactive-target", "verified-change", "archived-project"]
)
def test_github_username_permission_and_verified_identity_denials_have_no_effect(
    created_project, actors, client_for, guard
):
    project_id = created_project["id"]
    member = ProjectMember.objects.get(project_id=project_id, user_id=actors["member"])
    target = actors["leader"] if guard == "other-member" else actors["member"]
    caller = actors["member"]
    if guard == "inactive-target":
        member.status = "LEFT"
        member.left_at = timezone.now()
        member.save()
    if guard == "verified-change":
        member.github_username = "current"
        member.save(update_fields=["github_username"])
        assert (
            apply_account_fact(AccountFact(actors["member"], "github-user", "current", 2, True))
            == 1
        )
    if guard == "archived-project":
        Project.objects.filter(pk=project_id).update(archived_at=timezone.now())
    before = effect_state(project_id)
    members = list(ProjectMember.objects.order_by("id").values())
    reply = client_for(caller).patch(
        f"/projects/{project_id}/members/{target}/github/",
        {"github_username": "changed"},
        format="json",
    )
    assert reply.status_code == ({"other-member": 403, "inactive-target": 404}.get(guard, 400)), (
        reply.content
    )
    assert (
        effect_state(project_id) == before
        and list(ProjectMember.objects.order_by("id").values()) == members
    )


def test_same_declared_username_is_noop_and_does_not_upgrade_verification(
    created_project, actors, client_for
):
    route = f"/projects/{created_project['id']}/members/{actors['member']}/github/"
    client = client_for(actors["member"])
    first = client.patch(route, {"github_username": "student"}, format="json")
    assert first.status_code == 200
    before = effect_state(created_project["id"])
    second = client.patch(route, {"github_username": "student"}, format="json")
    assert second.json() == first.json() and not second.json()["data"]["is_github_verified"]
    assert effect_state(created_project["id"]) == before


def test_verification_request_for_removed_member_rolls_back_receipt_and_notification(
    created_project, actors, client_for
):
    project_id = created_project["id"]
    ProjectMember.objects.filter(project_id=project_id, user_id=actors["member"]).update(
        status="REMOVED", left_at=timezone.now()
    )
    before = effect_state(project_id)
    reply = client_for(actors["leader"]).post(
        f"/projects/{project_id}/members/{actors['member']}/github/request-verification/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="inactive-notification",
    )
    assert reply.status_code == 422 and reply.json()["error"]["code"] == "MEMBER_NOT_ACTIVE"
    assert effect_state(project_id) == before
