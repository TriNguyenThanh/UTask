from datetime import timedelta
from uuid import UUID

import pytest
from django.utils import timezone

from infrastructure.ai import VerifiedProposal


class FixtureAI:
    proposals = {}

    def verify(self, *, actor, project_id, proposal_id, kind, parent_id=None):
        return self.proposals[proposal_id]


@pytest.fixture
def ai(settings, actors):
    settings.WORK_AI_ADAPTER = "tests.fixtures.ai_proposals.FixtureAI"
    FixtureAI.proposals = {}

    def configure(
        project_id,
        *,
        proposal="proposal-1",
        kind="BACKLOG",
        parent_id=None,
        revisions=None,
        targets=(),
    ):
        proof = VerifiedProposal(
            project_id=UUID(str(project_id)),
            proposal_id=proposal,
            kind=kind,
            context_version=42,
            item_revisions=revisions or {"a": "r1", "b": "r1", "c": "r1", "action": "r1"},
            actor_ids=frozenset(actors.values()),
            expires_at=timezone.now() + timedelta(hours=1),
            parent_id=UUID(str(parent_id)) if parent_id else None,
            target_task_ids=frozenset(UUID(str(value)) for value in targets),
        )
        FixtureAI.proposals[proposal] = proof
        return proof

    return configure


def backlog_payload(project):
    return {
        "proposal_id": "proposal-1",
        "context_version": 42,
        "expected_project_version": project.version,
        "tasks": [
            {
                "local_id": "a",
                "ai_revision": "r1",
                "title": "Auth",
                "acceptance_criteria": "Login được",
            },
            {"local_id": "b", "ai_revision": "r1", "title": "API", "dependencies": ["a"]},
        ],
    }


def action_payload(*actions):
    return {
        "proposal_id": "proposal-1",
        "item_id": "action",
        "ai_revision": "r1",
        "context_version": 42,
        "actions": list(actions),
    }


def sprint_action(task, sprint, expected_sprint_version, *, action="ADD", reason="Reviewed scope"):
    return {
        "kind": "SPRINT_SCOPE",
        "task_id": task["id"],
        "expected_version": task["version"],
        "expected_sprint_version": expected_sprint_version,
        "sprint_id": sprint["id"],
        "scope_action": action,
        "reason": reason,
    }
