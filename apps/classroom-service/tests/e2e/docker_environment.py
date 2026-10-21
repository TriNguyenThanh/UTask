"""Owned Docker stack built from repository Compose and environment mappings."""

import base64
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .http_client import wait_until

ROOT = Path(__file__).resolve().parents[4]
SERVICES = (
    "postgres",
    "redis",
    "kafka",
    "identity-service",
    "classroom-service",
    "work-service",
    "work-publisher",
    "work-consumer",
    "classroom-work-consumer",
    "nginx",
)


class DockerEnvironment:
    def __init__(self, image_prefix, image_tag, output, keep=False):
        self.project = "classroom-e2e-" + uuid4().hex[:12]
        self.image_prefix, self.image_tag = image_prefix, image_tag
        self.output, self.keep = Path(output), keep
        self.temporary = None if keep else tempfile.TemporaryDirectory(prefix=self.project + "-")
        self.directory = Path(
            tempfile.mkdtemp(prefix=self.project + "-") if keep else self.temporary.name
        )
        self.config = self.directory / "compose.json"
        self.password = secrets.token_urlsafe(24) + "aA1!"
        self.gateway = None

    def __enter__(self):
        try:
            self.start()
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def docker(self, *args, input=None, timeout=240, check=True):
        result = subprocess.run(
            ["docker", *args],
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if check and result.returncode:
            raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
        return result

    def compose(self, *args, **kwargs):
        return self.docker("compose", "-p", self.project, "-f", str(self.config), *args, **kwargs)

    def configure(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_path = self.directory / "identity-private.pem"
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        key_path.chmod(0o644)
        template_names = {
            line.split("=", 1)[0]
            for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        values = {}
        classroom_caller = secrets.token_urlsafe(32)
        work_caller = secrets.token_urlsafe(32)
        values.update(
            {
                "UTASK_IMAGE_PREFIX": self.image_prefix,
                "UTASK_IMAGE_TAG": self.image_tag,
                "POSTGRES_USER": "classroom_e2e",
                "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
                "POSTGRES_HOST": "postgres",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "postgres",
                "DJANGO_ALLOWED_HOSTS": (
                    "localhost,127.0.0.1,identity-service,classroom-service,work-service"
                ),
                "IDENTITY_JWT_PRIVATE_KEY_HOST_PATH": key_path.as_posix(),
                "IDENTITY_MAIL_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
                "IDENTITY_MAIL_KEY_ID": "e2e",
                "IDENTITY_REDIS_URL": "redis://redis:6379/4",
                "IDENTITY_CLASSROOM_SERVICE_KEY": classroom_caller,
                "IDENTITY_WORK_SERVICE_KEY": work_caller,
                "CLASSROOM_WORK_SERVICE_KEY": secrets.token_urlsafe(32),
                "IDENTITY_SERVICE_KEYS": json.dumps(
                    {
                        "classroom": classroom_caller,
                        "work": work_caller,
                    }
                ),
                "CLASSROOM_ACCESS_CODE_HMAC_KEY": secrets.token_urlsafe(48),
                "IDENTITY_BASE_URL": "http://identity-service:8000",
                "CLASSROOM_BASE_URL": "http://classroom-service:8000",
                "WORK_CLASSROOM_DEV_ENABLED": "false",
                "WORK_CLASSROOM_ADAPTER": "infrastructure.classroom.RemoteClassroom",
                "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
                "KAFKA_CLUSTER_ID": base64.urlsafe_b64encode(secrets.token_bytes(16))
                .decode()
                .rstrip("="),
                "IDENTITY_AVATAR_ENABLED": "false",
                "IDENTITY_GOOGLE_ENABLED": "false",
                "IDENTITY_GITHUB_ENABLED": "false",
            }
        )
        for service in ("IDENTITY", "CLASSROOM", "WORK", "INTEGRATION", "NOTIFICATION"):
            values[service + "_DB_NAME"] = service.lower() + "_e2e"
            values[service + "_DJANGO_SECRET_KEY"] = secrets.token_urlsafe(48)
        env_path = self.directory / "stack.env"
        env_path.write_text(
            "\n".join(f"{k}='{v}'" for k, v in values.items()) + "\n", encoding="utf-8"
        )
        process_env = {
            k: v for k, v in os.environ.items() if k not in template_names | values.keys()
        }
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(ROOT / ".env.example"),
                "--env-file",
                str(env_path),
                "-f",
                str(ROOT / "docker-compose.yml"),
                "--profile",
                "work-service",
                "--profile",
                "classroom-service",
                "--profile",
                "kafka",
                "config",
                "--format",
                "json",
            ],
            cwd=ROOT,
            env=process_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError("Repository Compose configuration failed; secret output suppressed")
        source = json.loads(result.stdout)
        selected = {name: source["services"][name] for name in SERVICES}
        for service in selected.values():
            for field in ("build", "profiles", "container_name", "ports"):
                service.pop(field, None)
            service["restart"] = "no"
            service["networks"] = {"default": None}
            service["depends_on"] = {
                dep: condition
                for dep, condition in service.get("depends_on", {}).items()
                if dep in selected
            }
        selected["nginx"]["ports"] = [
            {
                "target": 80,
                "published": "0",
                "host_ip": "127.0.0.1",
                "protocol": "tcp",
            }
        ]
        configuration = {
            "services": selected,
            "networks": {"default": {}},
            "volumes": {name: {} for name in ("postgres_data", "redis_data", "kafka_data")},
        }
        self.config.write_text(json.dumps(configuration), encoding="utf-8")
        self.config.chmod(0o600)

    def start(self):
        self.configure()
        self.compose("up", "-d", "--wait", "--wait-timeout", "180", "postgres", "redis", "kafka")
        for service in ("identity", "classroom", "work"):
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                service + "-service",
                "/app/.venv/bin/python",
                "manage.py",
                "migrate",
                "--noinput",
            )
        # Kafka's repository startup creates the configured topics before health passes.
        self.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
        self.gateway = "http://" + self.compose("port", "nginx", "80").stdout.strip()
        wait_until(
            lambda: (
                requests.get(self.gateway + "/api/classroom/healthz", timeout=5).json()
                == {"status": "ok"}
            ),
            "gateway health",
        )

    def command(self, service, *args, capture=False):
        result = self.compose(
            "exec",
            "-T",
            service + "-service",
            "/app/.venv/bin/python",
            "manage.py",
            *args,
        )
        return result.stdout if capture else None

    def python(self, script, payload=None):
        return self.compose(
            "exec",
            "-T",
            "work-service",
            "/app/.venv/bin/python",
            "-c",
            script,
            input=json.dumps(payload),
            timeout=90,
        ).stdout

    def broker(self, action):
        self.compose(action, "kafka")

    def diagnostics(self):
        self.output.mkdir(parents=True, exist_ok=True)
        # No raw app logs/config: these can include tokens or access codes.
        rows = self.compose("ps", "-a", "--format", "json", check=False).stdout
        destination = self.output / self.project
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "docker-state.jsonl").write_text(rows, encoding="utf-8")
        (destination / "runtime.json").write_text(
            json.dumps(
                {
                    "project": self.project,
                    "image_prefix": self.image_prefix,
                    "image_tag": self.image_tag,
                    "kept": self.keep,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def close(self):
        try:
            if self.config.exists():
                try:
                    self.diagnostics()
                finally:
                    if not self.keep:
                        self.compose("down", "--volumes", "--remove-orphans", timeout=180)
                        for kind in ("container", "volume", "network"):
                            listing = self.docker(
                                kind,
                                "ls",
                                "--filter",
                                f"label=com.docker.compose.project={self.project}",
                                "-q",
                            )
                            if listing.stdout.strip():
                                raise RuntimeError(
                                    f"Owned E2E {kind} resources remain after cleanup"
                                )
        finally:
            if self.temporary is not None:
                self.temporary.cleanup()
