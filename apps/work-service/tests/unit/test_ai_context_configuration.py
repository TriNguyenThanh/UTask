"""Kiểm nạp cấu hình đóng quyền và pipeline env của Work, không đọc secret thật."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "configured,expected", [("{}", "dict"), ("{bad-json", "NoneType"), ("[]", "list")]
)
def test_service_key_setting_does_not_silently_allow_malformed_json(configured, expected):
    environment = {
        **os.environ,
        "WORK_SERVICE_KEYS": configured,
        "WORK_INTEGRATION_INBOUND_KEYS": "{bad-json",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from config.settings import base; "
            "print(type(base.WORK_SERVICE_KEYS).__name__); "
            "print(base.INTEGRATION_WORK_SERVICE_KEYS is None)",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [expected, "True"]
