"""Work + Integration real HTTP/DB/receipt; GitHub and Identity remain test doubles."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import requests
from psycopg import sql

from apps.integrations.models import GitHubConnectionOperation
from apps.integrations.services.operations import recover_operation
from apps.messaging.integration_consumer import process_connection_record
from apps.projects.models import Project

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def connection_topic():
    origin = os.environ.get("WORK_CONNECTION_TEST_KAFKA")
    if not origin:
        return
    from confluent_kafka import KafkaError, KafkaException
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": origin})
    topic = "utask.integration.events"
    try:
        admin.create_topics([NewTopic(topic, 1, 1)], request_timeout=10)[topic].result()
    except KafkaException as exc:
        if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
            raise
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = admin.list_topics(topic, timeout=3).topics.get(topic)
        if (
            state
            and state.error is None
            and state.partitions
            and all(partition.leader >= 0 for partition in state.partitions.values())
        ):
            return
        time.sleep(0.1)
    pytest.fail("Test connection topic has no ready partition")


@pytest.fixture
def integration_http(
    created_project, request, actors, settings, monkeypatch, tmp_path, connection_topic
):
    settings.STATIC_URL = "/static/"
    settings.MEDIA_URL = "/media/"
    live_server = request.getfixturevalue("live_server")
    db = settings.DATABASES["default"]
    name = "work_wire_" + uuid4().hex[:10] + "_test"
    admin = psycopg.connect(
        host=db["HOST"],
        port=db["PORT"],
        user=db["USER"],
        password=db["PASSWORD"],
        dbname="postgres",
        autocommit=True,
    )
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(name)))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ | {
        "INTEGRATION_TEST_DB_NAME": name,
        "INTEGRATION_TEST_DB_HOST": db["HOST"],
        "INTEGRATION_TEST_DB_PORT": str(db["PORT"]),
        "INTEGRATION_TEST_DB_USER": db["USER"],
        "INTEGRATION_TEST_DB_PASSWORD": db["PASSWORD"],
        "WIRE_ACTOR_ID": str(actors["leader"]),
        "WIRE_PORT": str(port),
        "WIRE_WORK_URL": live_server.url,
    }
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "integration_server.py"
    log_path = tmp_path / "provider.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(fixture)], env=env, stdout=log, stderr=log)
        try:
            origin = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, log_path.read_text(encoding="utf-8")
                try:
                    if requests.request("GET", origin + "/healthz", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                assert time.monotonic() < deadline, "Integration test server failed to start"
                time.sleep(0.1)
            settings.WORK_GITHUB_CONNECTION_ENABLED = True
            settings.INTEGRATION_ADAPTER = "infrastructure.integration.RemoteIntegration"
            settings.WORK_INTEGRATION_BASE_URL = origin
            settings.WORK_INTEGRATION_SERVICE_KEY = "w" * 32
            settings.INTEGRATION_WORK_SERVICE_KEYS = ["i" * 32]
            settings.STATIC_URL = "/static/"
            settings.MEDIA_URL = "/media/"
            monkeypatch.setattr(
                "apps.integrations.tasks.recover_connections.delay", lambda *args: None
            )
            yield origin
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
                )
            admin.close()


def test_real_services_connect_receipt_reference_disconnect(
    created_project, client_for, actors, integration_http
):
    leader = client_for(actors["leader"])
    route = f"/projects/{created_project['id']}/github/repository/"
    body = {
        "github_repo_id": "123",
        "operation_id": "wire-connect",
        "expected_connection_generation": 0,
    }
    result = leader.post(route, body, format="json")
    assert result.status_code == 202, result.content
    operation = GitHubConnectionOperation.objects.get(operation_id="wire-connect")
    assert recover_operation(operation.pk)
    project = Project.objects.get(pk=created_project["id"])
    assert project.github_connection_status == "CONNECTED"
    assert leader.post(route, body, format="json").json() == result.json()
    task_route = f"/projects/{project.pk}/tasks/"
    task = leader.post(
        task_route, {"title": "Wire task"}, format="json", HTTP_IDEMPOTENCY_KEY="wire-task"
    )
    assert task.status_code == 201, task.content
    link = leader.post(
        f"/tasks/{task.json()['data']['id']}/github-links/",
        {"link_type": "PULL_REQUEST", "github_ref_id": "#24"},
        format="json",
    )
    assert link.status_code == 201, link.content
    assert link.json()["data"]["confirmation_status"] == "CONFIRMED"
    disconnect = leader.delete(
        route,
        {"operation_id": "wire-disconnect", "expected_connection_generation": 1},
        format="json",
    )
    assert disconnect.status_code == 202, disconnect.content
    assert recover_operation(
        GitHubConnectionOperation.objects.get(operation_id="wire-disconnect").pk
    )
    project.refresh_from_db()
    assert project.github_connection_status == "DISCONNECTED"
    if os.environ.get("WORK_CONNECTION_TEST_KAFKA"):
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": os.environ["WORK_CONNECTION_TEST_KAFKA"],
                "group.id": "work-wire-" + uuid4().hex,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe(["utask.integration.events"])

        class DLQ:
            def publish(self, *args, **kwargs):
                raise AssertionError("Valid provider event must not reach DLQ")

        try:
            published = requests.request("POST", integration_http + "/__test__/publish", timeout=35)
            assert published.status_code == 200 and published.json()["published"] == 2
            seen = 0
            deadline = time.monotonic() + 20
            while seen < 2 and time.monotonic() < deadline:
                record = consumer.poll(1)
                if record is None:
                    continue
                assert not record.error(), record.error()
                import json

                if json.loads(record.value())["aggregate_id"] != str(project.pk):
                    continue
                process_connection_record(record, consumer, dlq=DLQ())
                seen += 1
            assert seen == 2
            project.refresh_from_db()
            assert project.github_connection_status == "DISCONNECTED"
        finally:
            consumer.close()


def test_real_kafka_empty_record_is_retried_before_offset_advances(monkeypatch):
    origin = os.environ.get("WORK_CONNECTION_TEST_KAFKA")
    if not origin:
        pytest.skip("Requires the isolated Kafka test broker")
    from types import SimpleNamespace
    from unittest.mock import Mock

    from confluent_kafka import Consumer, Producer, TopicPartition

    from apps.messaging.management.commands import consume_integration

    topic = "work-wire-empty-" + uuid4().hex
    config = {
        "bootstrap.servers": origin,
        "group.id": "work-wire-" + uuid4().hex,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
    }
    producer = Producer({"bootstrap.servers": origin, "message.timeout.ms": 10000})
    for value in (b"", b"{}"):
        producer.produce(topic, value=value)
    assert producer.flush(15) == 0
    client = Consumer(config)
    client.subscribe([topic])
    try:
        records = []
        deadline = time.monotonic() + 15
        while len(records) < 2 and time.monotonic() < deadline:
            record = client.poll(1)
            if record is not None:
                assert not record.error(), record.error()
                records.append(record)
        assert len(records) == 2 and not bool(records[0])
        wrapper = SimpleNamespace(
            subscribe=Mock(),
            poll=Mock(side_effect=[*records, KeyboardInterrupt()]),
            commit=client.commit,
            close=Mock(),
        )
        dlq = Mock()
        dlq.publish.side_effect = [RuntimeError("No DLQ ACK"), None, None]
        monkeypatch.setattr(consume_integration, "Consumer", lambda config: wrapper)
        monkeypatch.setattr(consume_integration, "DeadLetterPublisher", lambda **kwargs: dlq)
        monkeypatch.setattr(consume_integration.time, "sleep", lambda seconds: None)
        consume_integration.Command().handle()
        assert [call.args[0].value() for call in dlq.publish.call_args_list] == [b"", b"", b"{}"]
        assert client.committed([TopicPartition(topic, 0)], timeout=5)[0].offset == 2
    finally:
        client.close()


@pytest.mark.skipif(os.name == "nt", reason="Validates Docker/POSIX consumer signal lifecycle")
def test_work_consumer_runner_applies_three_sources_and_stops_children(
    project_payload,
    group,
    request,
    client_for,
    actors,
    connection_provider,
    connection_topic,
    settings,
    tmp_path,
):
    import json
    import signal
    from dataclasses import asdict, replace

    from confluent_kafka import Producer

    from apps.messaging.models import ConsumedEvent
    from apps.projects.models import UserProjection
    from common.serialization import json_value
    from infrastructure.classroom import GroupMemberFact, GroupSnapshot
    from tests.fixtures.classroom import FixtureClassroom, membership_event

    origin = os.environ.get("WORK_CONNECTION_TEST_KAFKA")
    if not origin:
        pytest.skip("Requires the isolated Kafka test broker")
    group_id, class_id = str(uuid4()), str(uuid4())
    FixtureClassroom.groups[group_id] = replace(group, group_id=group_id, class_id=class_id)
    project_payload["classroom_group_id"] = group_id
    created_project = request.getfixturevalue("created_project")
    project = Project.objects.get(pk=created_project["id"])
    result = client_for(actors["leader"]).post(
        f"/projects/{project.pk}/github/repository/",
        {
            "github_repo_id": "123",
            "operation_id": "runner-connect",
            "expected_connection_generation": 0,
        },
        format="json",
    )
    assert result.status_code == 202, result.content
    fact = replace(
        connection_provider.operations["runner-connect"]["fact"],
        status="CONNECTED",
        source_version=2,
    )
    stamp = fact.synced_at.isoformat()
    identity_id = uuid4()
    identity = {
        "event_id": str(uuid4()),
        "event_type": "identity.user.updated",
        "event_version": 1,
        "producer": "identity-service",
        "aggregate_id": str(identity_id),
        "occurred_at": stamp,
        "data": {"user_id": str(identity_id), "display_name": "Consumer test", "avatar_url": None},
    }
    classroom = membership_event(
        GroupSnapshot(
            group_id,
            class_id,
            2,
            (
                GroupMemberFact(actors["leader"], "LEADER"),
                GroupMemberFact(actors["member"], "MEMBER"),
            ),
        )
    )
    integration = {
        "event_id": str(uuid4()),
        "event_type": "integration.project.connection.changed",
        "event_version": 1,
        "producer": "integration-service",
        "aggregate_id": str(project.pk),
        "occurred_at": stamp,
        "trace_id": str(uuid4()),
        "payload": json_value(asdict(fact)),
    }
    identity_topic, classroom_topic = (
        "work-runner-identity-" + uuid4().hex,
        "work-runner-classroom-" + uuid4().hex,
    )
    publisher = Producer({"bootstrap.servers": origin, "message.timeout.ms": 10000})
    for topic, event in [
        (identity_topic, identity),
        (classroom_topic, classroom),
        ("utask.integration.events", integration),
    ]:
        publisher.produce(topic, value=json.dumps(event).encode())
    assert publisher.flush(15) == 0
    db = settings.DATABASES["default"]
    env = os.environ | {
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "WORK_TEST_DB_NAME": db["NAME"],
        "WORK_TEST_DB_USER": db["USER"],
        "WORK_TEST_DB_PASSWORD": db["PASSWORD"],
        "WORK_TEST_DB_HOST": db["HOST"],
        "WORK_TEST_DB_PORT": str(db["PORT"]),
        "KAFKA_BOOTSTRAP_SERVERS": origin,
        "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
        "WORK_IDENTITY_KAFKA_TOPIC": identity_topic,
        "WORK_CLASSROOM_KAFKA_TOPIC": classroom_topic,
        "WORK_CLASSROOM_KAFKA_GROUP": "runner-classroom-" + uuid4().hex,
        "WORK_INTEGRATION_KAFKA_GROUP": "runner-integration-" + uuid4().hex,
        "WORK_INTEGRATION_ADAPTER": "infrastructure.integration.RemoteIntegration",
        "WORK_GITHUB_CONNECTION_ENABLED": "false",
    }
    log_path = tmp_path / "work-consumer.log"
    with log_path.open("w", encoding="utf-8") as log:
        runner = subprocess.Popen(
            [sys.executable, "manage.py", "consume_work"], env=env, stdout=log, stderr=log
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert runner.poll() is None, log_path.read_text(encoding="utf-8")
                project.refresh_from_db()
                if (
                    project.group_source_version == 2
                    and project.github_connection_status == "CONNECTED"
                    and UserProjection.objects.filter(pk=identity_id).exists()
                ):
                    break
                time.sleep(0.1)
            else:
                pytest.fail(log_path.read_text(encoding="utf-8"))
            assert (
                ConsumedEvent.objects.filter(
                    event_id__in=[
                        identity["event_id"],
                        classroom["event_id"],
                        integration["event_id"],
                    ]
                ).count()
                == 3
            )
        finally:
            if os.name == "nt":
                runner.terminate()
            else:
                runner.send_signal(signal.SIGTERM)
            runner.wait(timeout=15)
        if os.name != "nt":
            assert runner.returncode == 0, log_path.read_text(encoding="utf-8")
