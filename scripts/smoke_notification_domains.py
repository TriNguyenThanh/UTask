"""Verify real Identity/Work -> Kafka -> Notification -> STARTTLS and gateway APIs.

Run with the Notification service's development Python after building its and
Identity/Work images with tag notification-verification. Uses root Compose mappings
with generated credentials and fresh databases/volumes; never reads .env/.env.staging
or sends real email. Pre-existing project/membership is a Work-owned test fixture.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "postgres",
    "redis",
    "kafka",
    "identity-service",
    "identity-publisher",
    "work-service",
    "work-publisher",
    "work-beat",
    "notification-migrate",
    "notification-service",
    "notification-worker",
    "notification-beat",
    "notification-identity-consumer",
    "notification-work-consumer",
    "nginx",
)


def wait_for(check, label, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Timed out: " + label)


def certificates(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    (directory / "identity.pem").write_bytes(pem)
    (directory / "smtp-key.pem").write_bytes(pem)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "smtp")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=5))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("smtp"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (directory / "smtp.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def main():
    project = "utask-notification-smoke-" + uuid4().hex[:10]
    report = {"project": project, "gmail": "not_tested", "staging": "not_tested"}
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        directory = Path(temporary)
        certificates(directory)
        sample = (ROOT / ".env.example").read_text(encoding="utf-8")
        environment = os.environ.copy()
        # Host service configuration cannot override this isolated test stack.
        for key in re.findall(r"^([A-Z][A-Z0-9_]*)=", sample, re.MULTILINE):
            environment.pop(key, None)
        mail_key = base64.b64encode(os.urandom(32)).decode()
        overrides = {
            "UTASK_IMAGE_TAG": "notification-verification",
            "UTASK_IMAGE_PREFIX": "utask",
            "POSTGRES_PASSWORD": secrets.token_hex(24),
            "IDENTITY_JWT_PRIVATE_KEY_HOST_PATH": (directory / "identity.pem").as_posix(),
            "IDENTITY_MAIL_KEY": mail_key,
            "IDENTITY_MAIL_KEY_ID": "smoke",
            "IDENTITY_REDIS_URL": "redis://redis:6379/0",
            "IDENTITY_WORK_SERVICE_KEY": secrets.token_hex(24),
            "IDENTITY_CLASSROOM_SERVICE_KEY": secrets.token_hex(24),
            "NOTIFICATION_SERVICE_TOKEN": secrets.token_hex(24),
            "IDENTITY_NOTIFICATION_SERVICE_KEY": secrets.token_hex(24),
            "NOTIFICATION_MAIL_KEYS": json.dumps({"smoke": mail_key}),
            "NOTIFICATION_IDENTITY_ENABLED": "true",
            "NOTIFICATION_WORK_ENABLED": "true",
            "NOTIFICATION_EMAIL_ENABLED": "true",
            "NOTIFICATION_EMAILS_PER_DAY": "1000",
            "NOTIFICATION_SMTP_HOST": "smtp",
            "NOTIFICATION_SMTP_PORT": "8025",
            "NOTIFICATION_SMTP_USERNAME": "fixture",
            "NOTIFICATION_SMTP_PASSWORD": "fixture",
            "NOTIFICATION_FROM_EMAIL": "fixture@example.test",
            "NOTIFICATION_FRONTEND_URL": "https://frontend.example.test",
            "IDENTITY_FRONTEND_URL": "https://frontend.example.test",
            "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
            "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
            "KAFKA_SSL_CA_LOCATION": "",
            "WORK_CLASSROOM_DEV_ENABLED": "false",
        }
        overrides["IDENTITY_SERVICE_KEYS"] = json.dumps(
            {
                "work": overrides["IDENTITY_WORK_SERVICE_KEY"],
                "classroom": overrides["IDENTITY_CLASSROOM_SERVICE_KEY"],
            }
        )
        # Compose dotenv uses single quoting for JSON and preserves its literal braces.
        env_file = directory / "smoke.env"
        env_file.write_text(
            sample
            + "\n"
            + "\n".join(key + "='" + value + "'" for key, value in overrides.items())
            + "\n",
            encoding="utf-8",
        )

        def command(args, *, data=None):
            try:
                result = subprocess.run(
                    args,
                    cwd=ROOT,
                    env=environment,
                    input=data,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    "Docker did not respond within the verification deadline"
                ) from None
            if result.returncode:
                # Subprocess output may include tokens or environment; never echo it.
                errors = re.findall(r"^([A-Za-z_.]+(?:Error|Exception)):", result.stderr, re.M)
                kind = errors[-1] if errors else "exit_" + str(result.returncode)
                action = next(
                    (part for part in args if part in {"up", "exec", "down", "config"}), "docker"
                )
                if action == "up":
                    # Compose startup messages contain service names/states, not app payloads.
                    for line in result.stderr.splitlines():
                        if re.fullmatch(
                            r"(?:dependency failed to start: )?container "
                            r"[a-zA-Z0-9_-]+ (?:is unhealthy|exited.*)",
                            line.strip(),
                            re.I,
                        ):
                            print(line.strip(), flush=True)
                    failed_ids = command(
                        [
                            "docker",
                            "ps",
                            "-aq",
                            "--filter",
                            "label=com.docker.compose.project=" + project,
                        ]
                    ).split()
                    for container_id in failed_ids:
                        state = command(
                            [
                                "docker",
                                "inspect",
                                container_id,
                                "--format",
                                "{{.Name}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} "
                                "health={{if .State.Health}}{{.State.Health.Status}}{{end}}",
                            ]
                        )
                        print(state.strip(), flush=True)
                        # Only print exception type names; never raw logs or credentials.
                        logs = subprocess.run(
                            ["docker", "logs", "--tail", "100", container_id],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=10,
                        )
                        kinds = sorted(
                            set(
                                re.findall(
                                    r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b",
                                    logs.stdout + logs.stderr,
                                )
                            )
                        )
                        if kinds:
                            print("Error types: " + ", ".join(kinds), flush=True)
                raise RuntimeError("Verification command failed: " + action + " (" + kind + ")")
            return result.stdout

        model = json.loads(
            command(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env_file),
                    "-f",
                    str(ROOT / "docker-compose.yml"),
                    "--profile",
                    "*",
                    "config",
                    "--format",
                    "json",
                ]
            )
        )
        model.pop("name", None)
        model["services"] = {k: model["services"][k] for k in SERVICES}
        for name, service in model["services"].items():
            service.pop("profiles", None)
            service.pop("build", None)
            service["restart"] = "no"
            service["ports"] = []
            service["depends_on"] = {
                k: v for k, v in service.get("depends_on", {}).items() if k in SERVICES
            }
            if name == "kafka":
                # Keep this fixture inside the memory left by the user's running stack.
                service["mem_limit"] = "512m"
                service.setdefault("environment", {}).update(
                    {
                        "KAFKA_HEAP_OPTS": "-Xms64m -Xmx192m",
                        "KAFKA_LOG_CLEANER_DEDUPE_BUFFER_SIZE": "16777216",
                        "JAVA_TOOL_OPTIONS": (
                            "-XX:MaxDirectMemorySize=64m -XX:MaxMetaspaceSize=128m"
                        ),
                    }
                )
            if name in {"identity-service", "work-service", "notification-service"}:
                service["command"] = [
                    "/app/.venv/bin/gunicorn",
                    "config.wsgi:application",
                    "--bind",
                    "0.0.0.0:8000",
                    "--workers",
                    "1",
                    "--preload",
                ]
            if name in {"work-publisher", "notification-worker"}:
                service["command"] += ["--pool=solo"]
            # Exercise this worktree while reusing the installed dependencies in the image.
            source_dirs = (
                ("notifications", "config")
                if name.startswith("notification-")
                else ("apps", "common")
                if name.startswith("work-")
                else ()
            )
            app = "notification-service" if name.startswith("notification-") else "work-service"
            for source_dir in source_dirs:
                service.setdefault("volumes", []).append(
                    {
                        "type": "bind",
                        "source": (ROOT / "apps" / app / source_dir).as_posix(),
                        "target": "/app/" + source_dir,
                        "read_only": True,
                    }
                )
            if name.startswith("notification-"):
                service.setdefault("volumes", []).append(
                    {
                        "type": "bind",
                        "source": directory.as_posix(),
                        "target": "/fixture",
                        "read_only": True,
                    }
                )
                service.setdefault("environment", {})["SSL_CERT_FILE"] = "/fixture/smtp.pem"
        # Let Docker assign loopback-only ports, avoiding the user's local/staging stack.
        for name, port in (("nginx", 80), ("postgres", 5432)):
            model["services"][name]["ports"] = [{"target": port, "host_ip": "127.0.0.1"}]
        fixture_mounts = [
            {
                "type": "bind",
                "source": str(ROOT / "scripts/tests/fixtures/notification_smtp.py"),
                "target": "/smtp.py",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": directory.as_posix(),
                "target": "/fixture",
                "read_only": True,
            },
        ]
        model["services"]["smtp"] = {
            "image": "utask/notification-service:notification-verification",
            "command": ["python", "/smtp.py"],
            "volumes": fixture_mounts,
            "ports": [{"target": 8080, "host_ip": "127.0.0.1"}],
        }
        # Remove explicit root project resource names; every volume/network is smoke-owned.
        for resources in (model.get("volumes", {}), model.get("networks", {})):
            for resource in resources.values():
                if isinstance(resource, dict):
                    resource.pop("name", None)
                    resource.pop("external", None)
        compose_file = directory / "compose.json"
        compose_file.write_text(json.dumps(model), encoding="utf-8")
        compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]

        def shell(service, code):
            output = command(
                compose
                + [
                    "exec",
                    "-T",
                    service,
                    "/app/.venv/bin/python",
                    "manage.py",
                    "shell",
                    "-c",
                    "import sys; exec(sys.stdin.read())",
                ],
                data=code,
            )
            line = output.strip().splitlines()[-1] if output.strip() else ""
            return json.loads(line) if line.startswith("{") else None

        def endpoint(service, port):
            return "http://" + command(compose + ["port", service, str(port)]).strip()

        try:
            print("Starting isolated real-domain Notification stack: " + project, flush=True)
            command(compose + ["up", "-d", "--wait", "--wait-timeout", "240"])
            base, mailbox = endpoint("nginx", 80), endpoint("smtp", 8080)

            def api(method, path, body=None, token=None, expected=200):
                headers = {"Authorization": "Bearer " + token} if token else {}
                headers["Idempotency-Key"] = str(uuid4()) if "/api/work/" in path else ""
                if not headers["Idempotency-Key"]:
                    del headers["Idempotency-Key"]
                response = requests.request(
                    method, base + path, json=body, headers=headers, timeout=15
                )
                if response.status_code != expected:
                    raise AssertionError(f"{method} {urlsplit(path).path}: {response.status_code}")
                return response.json()

            password = "SmokeStrongPassword123!"
            users = {}
            for role in ("leader", "member", "teacher", "pending"):
                body = {
                    "email": role + "@example.edu.vn",
                    "username": role,
                    "password1": password,
                    "password2": password,
                    "first_name": "Kiểm",
                    "last_name": "Thử",
                }
                created = api("POST", "/api/auth/register", body, expected=201)["data"]
                assert created["account_status"] == "ACTIVE"
                users[role] = created["user"]["id"]
            assert requests.get(mailbox, timeout=5).json() == []
            report["temporary_registration"] = "active_without_activation_mail"
            imported = shell(
                "identity-service",
                """
import json
from uuid import uuid4
from urllib.request import Request, urlopen
from django.conf import settings
from accounts.models import GlobalRole, OutboxEvent, User, UserGlobalRole
teacher = User.objects.get(email='teacher@example.edu.vn')
role, _ = GlobalRole.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})
UserGlobalRole.objects.get_or_create(user=teacher, role=role)
def post(path, body, headers=None):
    request = Request('http://127.0.0.1:8000' + path,
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', **(headers or {})}, method='POST')
    with urlopen(request, timeout=10) as response:
        return response.status, json.load(response)
status, login = post('/login',
    {'email': teacher.email, 'password': 'SmokeStrongPassword123!'})
assert status == 200
status, reply = post('/api/v1/internal/users/provision-students',
    {'students': [{'row_number': 1, 'email': '  IMPORTED@Example.EDU.VN  ',
                  'student_id': 'SMOKE001', 'first_name': 'Imported', 'last_name': 'Test'}]},
    headers={'Authorization': 'Bearer ' + login['data']['access'],
             'X-Service-Key': settings.IDENTITY_SERVICE_KEYS['classroom'],
             'Idempotency-Key': str(uuid4())})
assert status == 201
user = User.objects.get(email='imported@example.edu.vn')
assert user.account_status == 'ACTIVE' and user.is_email_verified
assert user.check_password(user.email)
assert not OutboxEvent.objects.filter(event_type__in=[
    'identity.activation.requested', 'identity.student.imported']).exists()
print(json.dumps({'status': user.account_status}))
""",
            )
            assert imported["status"] == "ACTIVE"
            api(
                "POST",
                "/api/auth/login",
                {"email": "imported@example.edu.vn", "password": "imported@example.edu.vn"},
            )
            assert requests.get(mailbox, timeout=5).json() == []
            report["temporary_import"] = "active_email_password_without_activation_mail"
            tokens = {
                role: api(
                    "POST",
                    "/api/auth/login",
                    {"email": role + "@example.edu.vn", "password": password},
                )["data"]["access"]
                for role in ("leader", "member")
            }
            setup = shell(
                "work-service",
                """
import json
from uuid import UUID, uuid4
from django.utils import timezone
from apps.projects.models import Project, ProjectMember, State
from apps.projects.services.projects import DEFAULT_STATES
p = Project.objects.create(identifier='SMOKE', name='Notification smoke',
                           classroom_group_id=str(uuid4()))
actors = json.loads('ACTORS')
for role in ('leader', 'member'):
    ProjectMember.objects.create(project=p, user_id=UUID(actors[role]), role=role.upper(),
                                 joined_at=timezone.now())
for i, (name, slug, color, group) in enumerate(DEFAULT_STATES):
    State.objects.create(project=p, name=name, slug=slug, color=color, group=group, sequence=i,
                         is_default=group == 'BACKLOG')
target = p.states.get(group='STARTED')
print(json.dumps({'project_id': str(p.pk), 'target_state_id': str(target.pk)}))
""".replace("ACTORS", json.dumps(users)),
            )
            pid = setup["project_id"]
            task = api(
                "POST",
                f"/api/work/projects/{pid}/tasks/",
                {
                    "title": "Kiểm chứng Notification",
                    "assignee_ids": [users["member"]],
                    "due_date": (datetime.now(UTC) + timedelta(hours=7)).date().isoformat(),
                },
                tokens["leader"],
                expected=201,
            )["data"]

            def feed():
                return api("GET", "/api/notifications/", token=tokens["member"])

            wait_for(lambda: feed()["count"] == 1, "real assignment in-app")
            wait_for(
                lambda: len(requests.get(mailbox, timeout=5).json()) == 1,
                "real assignment SMTP",
            )
            report["assignment"] = "real_http_outbox_kafka_in_app_smtp"
            notification_id = feed()["results"][0]["id"]
            api(
                "POST",
                f"/api/notifications/{notification_id}/read",
                token=tokens["member"],
            )
            assert (
                api("GET", "/api/notifications/unread-count", token=tokens["member"])["count"] == 0
            )
            api(
                "PATCH",
                "/api/notifications/preferences",
                {"mention": False},
                tokens["member"],
            )
            api(
                "POST",
                "/api/work/comments/",
                {
                    "task_id": task["id"],
                    "content_html": "<p>Nhắc thành viên</p>",
                    "mentioned_user_ids": [users["member"]],
                },
                tokens["leader"],
                expected=201,
            )
            wait_for(lambda: feed()["count"] == 2, "real mention in-app")
            shell(
                "work-service",
                "from apps.tasks.tasks import scan_deadlines; scan_deadlines()",
            )
            wait_for(lambda: feed()["count"] == 3, "real deadline in-app")
            wait_for(
                lambda: len(requests.get(mailbox, timeout=5).json()) == 2,
                "deadline SMTP",
            )
            api(
                "PATCH",
                f"/api/work/tasks/{task['id']}/transition/",
                {
                    "expected_version": task["version"],
                    "target_state_id": setup["target_state_id"],
                },
                tokens["leader"],
            )
            wait_for(lambda: feed()["count"] == 4, "real transition in-app")
            time.sleep(6)
            assert len(requests.get(mailbox, timeout=5).json()) == 2
            report["mention_deadline_transition_preferences"] = "passed"
            # Re-deliver the identical domain event through the actual Kafka producer.
            shell(
                "work-service",
                """
from apps.messaging.models import OutboxEvent
from infrastructure.kafka.client import KafkaPublisher
e = OutboxEvent.objects.filter(event_type='task.assigned').first()
KafkaPublisher().publish(e)
""",
            )
            time.sleep(6)
            assert feed()["count"] == 4
            assert len(requests.get(mailbox, timeout=5).json()) == 2
            report["duplicate"] = "no_additional_in_app_or_email"
            api("POST", "/api/notifications/read-all", token=tokens["member"])
            assert (
                api("GET", "/api/notifications/unread-count", token=tokens["member"])["count"] == 0
            )
            shell(
                "work-service",
                """
from django.utils import timezone
from apps.projects.models import ProjectMember
ProjectMember.objects.filter(user_id='MEMBER').update(status='REMOVED', left_at=timezone.now())
""".replace("MEMBER", users["member"]),
            )
            assert feed()["count"] == 0
            report["revoked_access"] = "hidden_by_real_work_resolver"
            # Reset is emitted by real Identity; only the SMTP fixture exposes the test link.
            api(
                "POST",
                "/api/auth/password-reset/request",
                {"email": "member@example.edu.vn"},
            )
            messages = wait_for(
                lambda: [
                    m
                    for m in requests.get(mailbox, timeout=5).json()
                    if m["subject"] == "Đặt lại mật khẩu UTask"
                ],
                "Identity reset SMTP",
            )
            link = re.search(
                r"https://frontend[.]example[.]test/auth/reset\?\S+",
                messages[0]["body"],
            )
            assert link
            query = {k: v[0] for k, v in parse_qs(urlsplit(link[0]).query).items()}
            api(
                "POST",
                "/api/auth/password-reset/confirm",
                {
                    **query,
                    "new_password1": "ChangedSmokePassword456!",
                    "new_password2": "ChangedSmokePassword456!",
                },
            )
            api(
                "POST",
                "/api/auth/login",
                {
                    "email": "member@example.edu.vn",
                    "password": "ChangedSmokePassword456!",
                },
            )
            api("GET", "/api/notifications/", token=tokens["member"], expected=401)
            report["password_reset"] = "smtp_link_confirmed_old_session_revoked"
            shell(
                "identity-service",
                """
from accounts.models import User
from allauth.account.models import EmailAddress
User.objects.filter(pk='PENDING_ID').update(account_status='PENDING_ACTIVATION')
EmailAddress.objects.filter(user_id='PENDING_ID').update(verified=False)
""".replace("PENDING_ID", users["pending"]),
            )
            api(
                "POST",
                "/api/auth/activation/resend",
                {"email": "pending@example.edu.vn"},
            )
            messages = wait_for(
                lambda: [
                    m
                    for m in requests.get(mailbox, timeout=5).json()
                    if m["subject"] == "Kích hoạt tài khoản UTask"
                ],
                "legacy activation SMTP",
            )
            link = re.search(
                r"https://frontend[.]example[.]test/auth/activate\?\S+",
                messages[0]["body"],
            )
            assert link
            activation = {k: v[0] for k, v in parse_qs(urlsplit(link[0]).query).items()}
            api("POST", "/api/auth/activate", activation)
            api(
                "POST",
                "/api/auth/login",
                {"email": "pending@example.edu.vn", "password": password},
            )
            report["legacy_activation"] = "smtp_link_confirmed"
            # Framework and serializer errors must be user-facing Vietnamese.
            error = api(
                "PATCH",
                "/api/notifications/preferences",
                {"mention": "yes"},
                tokens["leader"],
                expected=400,
            )
            assert "true hoặc false" in json.dumps(error, ensure_ascii=False)
            api("GET", "/api/notifications/", expected=401)
            assert (
                requests.post(
                    base + "/api/work/api/v1/internal/notifications/resolve",
                    json={},
                    timeout=5,
                ).status_code
                == 404
            )
            report["gateway_auth_validation"] = "passed"
            report["runtime"] = "passed"
            report["real_dependencies"] = [
                "Identity HTTP",
                "Work HTTP",
                "Kafka",
                "PostgreSQL",
                "Redis",
                "Celery",
                "Nginx",
                "SMTP STARTTLS",
            ]
            report["fixtures"] = [
                "pre-existing project/membership",
                "legacy pending account",
                "isolated SMTP mailbox",
            ]
            print(json.dumps(report, ensure_ascii=False), flush=True)
        finally:
            # This random project was created here; never target a user project/volume.
            try:
                command(compose + ["down", "--volumes", "--remove-orphans", "--timeout", "10"])
            except RuntimeError:
                print("Cleanup pending; inspect only Docker project " + project, flush=True)
                raise


if __name__ == "__main__":
    main()
