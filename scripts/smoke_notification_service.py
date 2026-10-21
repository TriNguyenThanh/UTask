"""Smoke runtime Notification with real Kafka/PostgreSQL/Redis and a TLS SMTP fixture.

Run using apps/notification-service/.venv/bin/python. Dependencies must be isolated:
NOTIFICATION_SMOKE_DB_* (HOST/PORT/USER/PASSWORD/NAME),
NOTIFICATION_SMOKE_KAFKA (default 127.0.0.1:55449),
NOTIFICATION_SMOKE_REDIS (default redis://127.0.0.1:56387/14).
Only a database ending _smoke_test is accepted. Identity/Work are HTTP stubs.
No Gmail credential or business data is used. All fixture secrets are ephemeral.
"""

from __future__ import annotations

import base64
import json
import os
import signal
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/notification-service"


def wait_for(check, label, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise RuntimeError("Timed out: " + label)


def main():
    database = os.environ.get("NOTIFICATION_SMOKE_DB_NAME", "notification_smoke_test")
    if not database.endswith("_smoke_test"):
        raise SystemExit("Refusing database without _smoke_test suffix")
    os.environ.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DJANGO_SECRET_KEY="ephemeral-smoke-only-signing-key-00000000",
        DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1",
        NOTIFICATION_DB_NAME=database,
        NOTIFICATION_DB_HOST=os.environ.get("NOTIFICATION_SMOKE_DB_HOST", "127.0.0.1"),
        NOTIFICATION_DB_PORT=os.environ.get("NOTIFICATION_SMOKE_DB_PORT", "55447"),
        NOTIFICATION_DB_USER=os.environ.get("NOTIFICATION_SMOKE_DB_USER", "utask_ci"),
        NOTIFICATION_DB_PASSWORD=os.environ.get("NOTIFICATION_SMOKE_DB_PASSWORD", ""),
        NOTIFICATION_REDIS_URL=os.environ.get(
            "NOTIFICATION_SMOKE_REDIS", "redis://127.0.0.1:56387/14"
        ),
        KAFKA_BOOTSTRAP_SERVERS=os.environ.get(
            "NOTIFICATION_SMOKE_KAFKA", "127.0.0.1:55449"
        ),
        NOTIFICATION_IDENTITY_ENABLED="true",
        NOTIFICATION_WORK_ENABLED="true",
        NOTIFICATION_EMAIL_ENABLED="true",
        SMTP_USERNAME="fixture",
        SMTP_PASSWORD="fixture",
        SMTP_FROM_EMAIL="utask@example.test",
        NOTIFICATION_SERVICE_TOKEN="fixture-service-token-0000000000000000000000",
        IDENTITY_NOTIFICATION_SERVICE_KEY="fixture-session-key-0000000000000000000000",
        NOTIFICATION_FRONTEND_URL="https://frontend.example.test",
    )
    sys.path.insert(0, str(APP))
    import django
    import jwt
    import requests
    from confluent_kafka import Producer
    from confluent_kafka.admin import AdminClient, NewTopic
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    user_id, project_id, task_id = str(uuid4()), str(uuid4()), str(uuid4())
    key = os.urandom(32)
    os.environ["NOTIFICATION_MAIL_KEYS"] = json.dumps(
        {"smoke": base64.b64encode(key).decode()}
    )
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update(kid="smoke", use="sig", alg="RS256")
    state = {"eligible": True, "messages": [], "drop_reply": False}

    class Domain(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.reply({"keys": [jwk]})

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw or b"{}")
            if self.path.endswith("session-status"):
                assert (
                    self.headers.get("X-Service-Key")
                    == "fixture-session-key-0000000000000000000000"
                )
                self.reply({"success": True, "data": {"active": True}})
            elif self.path.endswith("notification-contacts"):
                assert (
                    self.headers.get("X-Service-Token")
                    == "fixture-service-token-0000000000000000000000"
                )
                self.reply(
                    {
                        "users": [
                            {
                                "user_id": uid,
                                "email": "recipient@example.test",
                                "display_name": "Kiểm thử",
                                "account_status": "ACTIVE",
                            }
                            for uid in body["user_ids"]
                        ]
                    }
                )
            else:
                assert (
                    self.headers.get("X-Service-Token")
                    == "fixture-service-token-0000000000000000000000"
                )
                result = {
                    "eligible": state["eligible"],
                    "title": "Được giao công việc",
                    "body": "Công việc <kiểm thử>",
                    "target": {
                        "kind": "board-issue",
                        "projectId": project_id,
                        "issueKey": "TEST-1",
                    },
                }
                self.reply(
                    {"results": [result for _ in body["items"]]}
                    if "items" in body
                    else result
                )

        def reply(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    children = []
    with tempfile.TemporaryDirectory(prefix="utask-notification-smoke-") as directory:
        path = Path(directory)
        cert, cert_key = path / "cert.pem", path / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-keyout",
                str(cert_key),
                "-out",
                str(cert),
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, cert_key)

        class SMTP(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 localhost fixture\r\n")
                self.wfile.flush()
                while line := self.rfile.readline():
                    command = line.upper().split(b" ", 1)[0].strip()
                    if command == b"EHLO":
                        self.wfile.write(
                            b"250-localhost\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n"
                        )
                    elif command == b"STARTTLS":
                        self.wfile.write(b"220 Begin TLS\r\n")
                        self.wfile.flush()
                        wrapped = context.wrap_socket(self.connection, server_side=True)
                        self.connection = wrapped
                        self.rfile = wrapped.makefile("rb")
                        self.wfile = wrapped.makefile("wb")
                    elif command == b"AUTH":
                        self.wfile.write(b"235 Authenticated\r\n")
                    elif command in {b"MAIL", b"RCPT", b"RSET", b"NOOP"}:
                        self.wfile.write(b"250 OK\r\n")
                    elif command == b"DATA":
                        self.wfile.write(b"354 End with dot\r\n")
                        self.wfile.flush()
                        parts = []
                        while (data := self.rfile.readline()) not in {b".\r\n", b""}:
                            parts.append(data)
                        state["messages"].append(b"".join(parts))
                        if state["drop_reply"]:
                            return
                        self.wfile.write(b"250 Accepted\r\n")
                    elif command == b"QUIT":
                        self.wfile.write(b"221 Bye\r\n")
                        self.wfile.flush()
                        return
                    else:
                        self.wfile.write(b"500 Unsupported\r\n")
                    self.wfile.flush()

        smtp = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SMTP)
        domain = ThreadingHTTPServer(("127.0.0.1", 0), Domain)
        for server in (smtp, domain):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ.update(
            SMTP_HOST="localhost",
            SMTP_PORT=str(smtp.server_address[1]),
            SSL_CERT_FILE=str(cert),
            IDENTITY_BASE_URL=f"http://127.0.0.1:{domain.server_port}",
            WORK_BASE_URL=f"http://127.0.0.1:{domain.server_port}",
        )
        django.setup()
        from django.core.management import call_command
        from notifications.models import EmailDelivery, Inbox, Notification, Quarantine

        call_command("migrate", verbosity=0)
        if Inbox.objects.exists():
            raise RuntimeError(
                "Smoke database must be empty; create a fresh isolated database"
            )
        topic_suffix = uuid4().hex[:10]
        os.environ.update(
            KAFKA_IDENTITY_TOPIC="smoke.identity." + topic_suffix,
            KAFKA_WORK_TOPIC="smoke.work." + topic_suffix,
        )
        # Child settings load the isolated topic names; parent only uses ORM.
        admin = AdminClient(
            {"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"]}
        )
        topics = [os.environ["KAFKA_IDENTITY_TOPIC"], os.environ["KAFKA_WORK_TOPIC"]]
        for future in admin.create_topics(
            [NewTopic(topic, 1, 1) for topic in topics]
        ).values():
            future.result(timeout=30)
        logs = (path / "runtime.log").open("w+")
        try:
            for args in (
                ["manage.py", "consume_notifications", "--source", "identity"],
                ["manage.py", "consume_notifications", "--source", "work"],
                [
                    "-m",
                    "celery",
                    "-A",
                    "config",
                    "worker",
                    "-Q",
                    "notification",
                    "--pool=solo",
                    "--concurrency=1",
                    "--loglevel=WARNING",
                ],
                [
                    "-m",
                    "celery",
                    "-A",
                    "config",
                    "beat",
                    "--pidfile=" + str(path / "beat.pid"),
                    "--schedule=" + str(path / "beat"),
                    "--loglevel=WARNING",
                ],
            ):
                children.append(
                    subprocess.Popen(
                        [sys.executable, *args],
                        cwd=APP,
                        stdout=logs,
                        stderr=logs,
                        start_new_session=True,
                    )
                )
            with socket.socket() as free:
                free.bind(("127.0.0.1", 0))
                api_port = free.getsockname()[1]
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "gunicorn",
                        "config.wsgi:application",
                        "--bind",
                        f"127.0.0.1:{api_port}",
                    ],
                    cwd=APP,
                    stdout=logs,
                    stderr=logs,
                    start_new_session=True,
                )
            )
            base = f"http://127.0.0.1:{api_port}"
            wait_for(
                lambda: requests.get(base + "/healthz", timeout=2).status_code == 200,
                "API readiness",
            )
            producer = Producer(
                {"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"]}
            )

            def publish(envelope, topic=topics[0]):
                errors = []
                producer.produce(
                    topic,
                    json.dumps(envelope).encode(),
                    callback=lambda err, _: errors.append(err) if err else None,
                )
                assert producer.flush(10) == 0 and not errors

            def identity(expired=False):
                event_id = str(uuid4())
                expiry = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=-10 if expired else 600)
                ).isoformat()
                nonce = os.urandom(12)
                aad = json.dumps(
                    [event_id, "identity.password_reset.requested", user_id, expiry],
                    separators=(",", ":"),
                ).encode()
                secret = {
                    "key_id": "smoke",
                    "expires_at": expiry,
                    "nonce": base64.b64encode(nonce).decode(),
                    "ciphertext": base64.b64encode(
                        AESGCM(key).encrypt(
                            nonce,
                            b'{"uid":"smoke-user","token":"smoke-reset-token"}',
                            aad,
                        )
                    ).decode(),
                }
                return {
                    "event_id": event_id,
                    "event_type": "identity.password_reset.requested",
                    "event_version": 1,
                    "aggregate_id": user_id,
                    "aggregate_type": "user",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "trace_id": str(uuid4()),
                    "producer": "identity-service",
                    "data": {
                        "user_id": user_id,
                        "email": "recipient@example.test",
                        "expires_at": expiry,
                        "secret": None if expired else secret,
                    },
                }

            first = identity()
            publish(first)
            wait_for(
                lambda: EmailDelivery.objects.filter(
                    inbox__event_id=first["event_id"], status="accepted_by_smtp"
                ).exists(),
                "Identity mail accepted",
            )
            assert len(state["messages"]) == 1
            publish(first)
            time.sleep(6)
            assert (
                len(state["messages"]) == 1
                and Inbox.objects.filter(event_id=first["event_id"]).count() == 1
            )
            expired = identity(True)
            publish(expired)
            wait_for(
                lambda: (
                    EmailDelivery.objects.filter(inbox__event_id=expired["event_id"])
                    .exclude(status__in=["pending", "sending"])
                    .exists()
                ),
                "expired mail terminal",
            )
            assert len(state["messages"]) == 1
            state["drop_reply"] = True
            unknown = identity()
            publish(unknown)
            wait_for(
                lambda: EmailDelivery.objects.filter(
                    inbox__event_id=unknown["event_id"], status="delivery_unknown"
                ).exists(),
                "ambiguous SMTP is terminal",
            )
            state["drop_reply"] = False
            time.sleep(6)
            assert len(state["messages"]) == 2
            work = {
                "event_id": str(uuid4()),
                "event_type": "task.assigned",
                "event_version": 1,
                "aggregate_id": task_id,
                "project_id": project_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "trace_id": str(uuid4()),
                "producer": "work-service",
                "entity_version": 1,
                "project_sequence": 1,
                "data": {
                    "task_id": task_id,
                    "actor_user_id": str(uuid4()),
                    "recipient_ids": [user_id],
                },
            }
            publish(work, topics[1])
            wait_for(
                lambda: Notification.objects.filter(
                    inbox__event_id=work["event_id"]
                ).exists(),
                "in-app notification",
            )
            wait_for(
                lambda: EmailDelivery.objects.filter(
                    inbox__event_id=work["event_id"], status="accepted_by_smtp"
                ).exists(),
                "Work mail accepted",
            )
            pem = private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            bearer = jwt.encode(
                {
                    "sub": user_id,
                    "token_type": "access",
                    "iss": "https://identity.utask.internal",
                    "aud": "utask-platform",
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                },
                pem,
                algorithm="RS256",
                headers={"kid": "smoke"},
            )
            headers = {"Authorization": "Bearer " + bearer}
            result = requests.get(base + "/", headers=headers, timeout=10)
            assert result.status_code == 200 and result.json()["count"] == 1
            notification_id = result.json()["results"][0]["id"]
            assert (
                requests.post(
                    base + f"/{notification_id}/read", headers=headers, timeout=10
                ).status_code
                == 200
            )
            assert (
                requests.get(
                    base + "/unread-count", headers=headers, timeout=10
                ).json()["count"]
                == 0
            )
            state["eligible"] = False
            assert (
                requests.get(base + "/", headers=headers, timeout=10).json()["count"]
                == 0
            )
            publish({"event_id": str(uuid4()), "event_version": 2})
            wait_for(lambda: Quarantine.objects.exists(), "malformed event quarantine")
            print(
                json.dumps(
                    {
                        "runtime": "passed",
                        "identity_mail": "accepted",
                        "duplicate": "deduplicated",
                        "expired": "not_sent",
                        "ambiguous_smtp": "not_retried",
                        "work_mail": "accepted",
                        "in_app": "read_and_revoked",
                        "malformed": "quarantined",
                        "real_dependencies": [
                            "Kafka",
                            "PostgreSQL",
                            "Redis",
                            "Celery",
                            "SMTP STARTTLS",
                        ],
                        "stub_dependencies": ["Identity HTTP", "Work HTTP"],
                        "gmail": "not_tested",
                    }
                )
            )
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
            for child in children:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            for server in (smtp, domain):
                server.shutdown()
                server.server_close()
            admin.delete_topics(topics)
            logs.close()


if __name__ == "__main__":
    main()
