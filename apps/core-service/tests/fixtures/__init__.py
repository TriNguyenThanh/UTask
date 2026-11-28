"""Shared in-memory external-boundary fakes for UTask Core Service tests."""

from tests.fixtures.ai_proposals import FakeAIProposals, FixtureAI, action_payload, backlog_payload
from tests.fixtures.integration import FakeIntegration, FixtureIntegration
from tests.fixtures.storage import FixtureStorage, InMemoryStorage

__all__ = [
    "FakeAIProposals",
    "FakeIntegration",
    "FixtureAI",
    "FixtureIntegration",
    "FixtureStorage",
    "InMemoryStorage",
    "action_payload",
    "backlog_payload",
]
