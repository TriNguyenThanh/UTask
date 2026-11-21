"""Kiểm nạp cấu hình đóng quyền và pipeline env của Work, không đọc secret thật."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from common.service_permissions import valid_keys


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


def test_work_key_mapping_uses_existing_compose_env_files_and_private_gateway():
    root = Path(__file__).resolve().parents[4]
    mapping = (root / "infra/env/work-service.env").read_text("utf-8")
    assert "WORK_SERVICE_KEYS=${WORK_SERVICE_KEYS:-{}}" in mapping
    example = (root / ".env.example").read_text("utf-8")
    example_values = dict(
        line.split("=", 1)
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    configured = json.loads(example_values["WORK_SERVICE_KEYS"].strip("'\""))
    assert example_values["AI_WORK_SERVICE_AUTH_ENABLED"] == "true"
    assert set(configured) == {"ai"}
    assert valid_keys(configured["ai"])
    assert configured["ai"] == [example_values["AI_WORK_SERVICE_KEY"].strip("'\"")]
    for filename in ("docker-compose.yml", "docker-compose.staging.yml"):
        services = yaml.safe_load((root / filename).read_text("utf-8"))["services"]
        work = services["work-service"]
        assert "./infra/env/work-service.env" in work["env_file"]
        assert ["python", "manage.py", "consume_work"] == services["work-consumer"]["command"]
        assert not any(
            "WORK_SERVICE_KEYS" in service.get("environment", {}) for service in services.values()
        )
    gateway = (root / "infra/nginx/nginx.conf").read_text("utf-8")
    assert "location ^~ /api/work/api/v1/internal/" in gateway
