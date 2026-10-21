from dataclasses import asdict, replace

import pytest
from django.utils import timezone

from common.errors import WorkError
from common.serialization import json_value
from infrastructure.integration import ConnectionFact


class ConnectionProvider:
    def __init__(self):
        self.operations = {}
        self.prepare_calls = 0
        self.after_prepare = None
        self.lose_confirm = False

    def prepare(self, *, project_id, body, bearer):
        self.prepare_calls += 1
        key = body["operation_id"]
        if key not in self.operations:
            fact = ConnectionFact(
                project_id,
                key,
                body["expected_generation"] + 1,
                2 * body["expected_generation"] + 1,
                "PENDING",
                body["github_repo_id"],
                "team" if body["action"] == "CONNECT" else None,
                "repo" if body["action"] == "CONNECT" else None,
                "main" if body["action"] == "CONNECT" else None,
                timezone.now(),
            )
            self.operations[key] = {"fact": fact, "action": body["action"], "state": "PREPARED"}
        if self.after_prepare:
            self.after_prepare()
        return self.operations[key]["fact"]

    def status(self, *, project_id, operation_id):
        if operation_id not in self.operations:
            raise WorkError("INTEGRATION_404", "Không tìm thấy yêu cầu.", 404)
        op = self.operations[operation_id]
        return {
            "project_id": str(project_id),
            "operation_id": operation_id,
            "action": op["action"],
            "state": op["state"],
            "generation": op["fact"].generation,
            "expires_at": timezone.now().isoformat(),
            "result": json_value(asdict(op["fact"])),
        }

    def confirm(self, *, project_id, operation_id, generation):
        op = self.operations[operation_id]
        if op["state"] == "PREPARED":
            op["fact"] = replace(
                op["fact"],
                status="CONNECTED" if op["action"] == "CONNECT" else "DISCONNECTED",
                source_version=op["fact"].source_version + 1,
            )
            op["state"] = "CONFIRMED"
        if self.lose_confirm:
            self.lose_confirm = False
            raise WorkError("INTEGRATION_UNAVAILABLE", "Chưa thể xác minh.", 503)
        return op["fact"]

    def abort(self, *, project_id, operation_id, generation):
        self.operations[operation_id]["state"] = "ABORTED"
        return self.status(project_id=project_id, operation_id=operation_id)


@pytest.fixture
def connection_provider(settings, monkeypatch):
    settings.WORK_GITHUB_CONNECTION_ENABLED = True
    settings.WORK_INTEGRATION_SERVICE_KEY = "w" * 32
    settings.INTEGRATION_WORK_SERVICE_KEYS = ["i" * 32]
    provider = ConnectionProvider()
    monkeypatch.setattr(
        "apps.integrations.services.operations.integration_client", lambda: provider
    )
    monkeypatch.setattr("apps.integrations.tasks.recover_connections.delay", lambda *args: None)
    return provider
