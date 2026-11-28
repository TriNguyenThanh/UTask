"""Fake AI proposal verification adapter matching infrastructure.ai signatures."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from django.utils import timezone

from common.errors import CoreAPIError
from infrastructure.ai import VerifiedProposal


class FakeAIProposals:
    """In-memory fake compatible with infrastructure.ai.RemoteProposals."""

    accepts_bearer = True
    proposals: dict[str, VerifiedProposal | Exception] = {}
    calls: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls.proposals = {}
        cls.calls = []

    @classmethod
    def register(
        cls,
        project_id: UUID | str,
        *,
        actor_ids: Iterable[UUID | str],
        proposal_id: str = "proposal-1",
        kind: str = "BACKLOG",
        context_version: int = 42,
        item_revisions: dict[str, str] | None = None,
        parent_id: UUID | str | None = None,
        target_task_ids: Iterable[UUID | str] = (),
        expires_at=None,
    ) -> VerifiedProposal:
        proof = VerifiedProposal(
            project_id=UUID(str(project_id)),
            proposal_id=proposal_id,
            kind=kind,
            context_version=context_version,
            item_revisions=dict(
                item_revisions or {"a": "r1", "b": "r1", "c": "r1", "action": "r1"}
            ),
            actor_ids=frozenset(UUID(str(actor_id)) for actor_id in actor_ids),
            expires_at=expires_at or (timezone.now() + timedelta(hours=1)),
            parent_id=UUID(str(parent_id)) if parent_id is not None else None,
            target_task_ids=frozenset(UUID(str(task_id)) for task_id in target_task_ids),
        )
        cls.proposals[proposal_id] = proof
        return proof

    @classmethod
    def register_error(cls, proposal_id: str, error: Exception) -> None:
        cls.proposals[proposal_id] = error

    def verify(
        self,
        *,
        actor,
        project_id,
        proposal_id: str,
        kind: str,
        parent_id=None,
        bearer: str | None = None,
    ) -> VerifiedProposal:
        self.calls.append(
            {
                "actor": actor,
                "project_id": project_id,
                "proposal_id": proposal_id,
                "kind": kind,
                "parent_id": parent_id,
                "bearer": bearer,
            }
        )
        entry = self.proposals.get(proposal_id)
        if entry is None:
            raise CoreAPIError(
                "AI_PROPOSAL_NOT_FOUND",
                "Không tìm thấy đề xuất AI được yêu cầu.",
                status_code=404,
            )
        if isinstance(entry, Exception):
            raise entry
        return entry


FixtureAI = FakeAIProposals


@pytest.fixture
def ai_proposals(settings):
    """Configure Core Service to use FakeAIProposals and return the fake adapter class."""
    settings.WORK_AI_ADAPTER = "tests.fixtures.ai_proposals.FakeAIProposals"
    FakeAIProposals.reset()
    yield FakeAIProposals
    FakeAIProposals.reset()


def backlog_payload(project, *, proposal_id: str = "proposal-1", context_version: int = 42) -> dict:
    return {
        "proposal_id": proposal_id,
        "context_version": context_version,
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


def action_payload(
    *actions: dict[str, Any],
    proposal_id: str = "proposal-1",
    item_id: str = "action",
    ai_revision: str = "r1",
    context_version: int = 42,
) -> dict[str, Any]:
    return {
        "proposal_id": proposal_id,
        "item_id": item_id,
        "ai_revision": ai_revision,
        "context_version": context_version,
        "actions": list(actions),
    }
