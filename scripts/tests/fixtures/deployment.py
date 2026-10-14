"""Isolated Docker/SSH stand-ins for exercising the real staging shell script."""

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INPUT_NAMES = (
    "registry_token",
    "registry",
    "registry_user",
    "image_prefix",
    "image_tag",
    "service_names",
    "migration_names",
    "gateway_names",
    "infrastructure_names",
    "gateway_service",
)


@contextmanager
def deployment_runtime(
    *,
    services="identity-service",
    migrations="identity-service",
    paths="/api/auth/healthz",
    fail_on="",
    fail_code=1,
):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".env").write_text("TEST_ONLY=true\n")
        (root / "infra/nginx").mkdir(parents=True)
        (root / "infra/nginx/nginx.deployment.conf").write_text("test-only config\n")
        (root / "infra/nginx/nginx.conf").write_text("current config\n")
        (root / "staging-images.json").write_text(
            json.dumps(
                {
                    "services": {
                        service: {
                            "image": "test/utask/" + service + "@sha256:" + "a" * 64
                        }
                        for service in services.split()
                    }
                }
            )
        )
        (root / "scripts").mkdir()
        shutil.copyfile(
            ROOT / "scripts/deploy_staging.sh", root / "scripts/deploy_staging.sh"
        )
        calls = root / "docker-calls"
        docker = root / "docker"
        docker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args=sys.argv[1:]\n"
            "if 'login' in args and sys.stdin.read().rstrip('\\n') != os.environ['EXPECTED_REGISTRY_TOKEN']: sys.exit(2)\n"
            "with open(os.environ['CALLS'], 'a') as output: output.write(json.dumps(args) + '\\n')\n"
            "stage='migration' if 'migrate' in args else 'up' if 'up' in args else 'reload' if 'nginx' in args and '-s' in args else 'nginx' if 'nginx' in args and '-t' in args else 'gateway' if '-c' in args else ''\n"
            "if stage and stage == os.environ['FAIL_ON']: sys.exit(int(os.environ['FAIL_CODE']))\n"
            "if 'run' in args: sys.stdin.read()\n"
            "if 'config' in args and '--services' in args: print(os.environ['EXPECTED_SERVICE_NAMES'].replace(' ', '\\n') + '\\n' + os.environ['EXPECTED_GATEWAY_SERVICE'])\n"
        )
        docker.chmod(0o755)
        ssh = root / "ssh"
        ssh.write_text(
            "#!/usr/bin/env python3\n"
            "import subprocess, sys\n"
            "workdir=sys.stdin.buffer.readline().rstrip(b'\\n').decode()\n"
            "raise SystemExit(subprocess.run(['bash',workdir+'/scripts/deploy_staging.sh',workdir],input=sys.stdin.buffer.read(),check=False).returncode)\n"
        )
        ssh.chmod(0o755)
        env = {
            **os.environ,
            "PATH": directory + os.pathsep + os.environ["PATH"],
            "CALLS": str(calls),
            "FAIL_ON": fail_on,
            "FAIL_CODE": str(fail_code),
            "registry_token": "test-token",
            "EXPECTED_REGISTRY_TOKEN": "test-token",
            "EXPECTED_SERVICE_NAMES": services,
            "EXPECTED_GATEWAY_SERVICE": "nginx",
            "registry": "test.invalid",
            "registry_user": "test",
            "image_prefix": "test/utask",
            "image_tag": "sha-test",
            "service_names": services,
            "migration_names": migrations,
            "gateway_names": paths,
            "infrastructure_names": "postgres redis queue",
            "gateway_service": "nginx",
        }
        yield root, env, calls


def run_staging_deploy(root, env, *, inputs=None):
    if inputs is None:
        inputs = {name: env[name] for name in reversed(INPUT_NAMES)}
    return subprocess.run(
        ["bash", str(root / "scripts/deploy_staging.sh"), str(root)],
        input="".join(f"{name}={value}\n" for name, value in inputs.items()),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def docker_calls(path):
    return [json.loads(line) for line in path.read_text().splitlines()]
