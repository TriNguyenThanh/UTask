"""Work connection configuration: one consumer container and private receipt."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WorkIntegrationConfigurationTests(unittest.TestCase):

    def test_work_mapping_contains_only_variable_references_and_safe_defaults(self):
        text = (ROOT / "infra/env/work-service.env").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in [
            "WORK_INTEGRATION_BASE_URL",
            "WORK_INTEGRATION_SERVICE_KEY",
            "WORK_INTEGRATION_INBOUND_KEYS",
            "WORK_GITHUB_CONNECTION_ENABLED",
            "WORK_INTEGRATION_KAFKA_GROUP",
            "WORK_INTEGRATION_DLQ_TOPIC",
        ]:
            self.assertIn(name + "=${", text)
            self.assertIn(name + "=", example)
        self.assertIn(
            "WORK_GITHUB_CONNECTION_ENABLED=${WORK_GITHUB_CONNECTION_ENABLED:-false}",
            text,
        )
        self.assertIn("infrastructure.integration.UnavailableIntegration", text)





if __name__ == "__main__":
    unittest.main()
