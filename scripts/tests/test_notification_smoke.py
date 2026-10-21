"""Small helper tests; the smoke runner itself is verified against real services."""

import unittest
from unittest.mock import patch

from scripts.smoke_notification_service import wait_for


class NotificationSmokeHelperTests(unittest.TestCase):
    def test_wait_returns_success_after_transient_failure(self):
        with patch("scripts.smoke_notification_service.time.sleep"):
            answers = iter([OSError("not ready"), False, "ready"])

            def check():
                answer = next(answers)
                if isinstance(answer, OSError):
                    raise answer
                return answer

            self.assertEqual(wait_for(check, "fixture"), "ready")

    def test_wait_timeout_names_failed_dependency(self):
        with self.assertRaisesRegex(RuntimeError, "Timed out: fixture"):
            wait_for(lambda: False, "fixture", seconds=0)

    def test_wait_propagates_programming_errors(self):
        with self.assertRaises(KeyError):
            wait_for(lambda: {}["missing"], "fixture")
