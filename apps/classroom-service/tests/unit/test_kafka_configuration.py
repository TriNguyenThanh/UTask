import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.messaging.management.commands import consume_work
from infrastructure import kafka

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def kafka_settings(settings):
    settings.KAFKA_BOOTSTRAP_SERVERS = "isolated-broker.test:9092"
    settings.KAFKA_SECURITY_PROTOCOL = "PLAINTEXT"
    settings.KAFKA_SASL_MECHANISM = "PLAIN"
    settings.KAFKA_SASL_USERNAME = ""
    settings.KAFKA_SASL_PASSWORD = ""
    settings.KAFKA_SSL_CA_LOCATION = ""
    return settings


def test_settings_default_to_local_plaintext(monkeypatch):
    names = (
        "KAFKA_SECURITY_PROTOCOL",
        "KAFKA_SASL_MECHANISM",
        "KAFKA_SASL_USERNAME",
        "KAFKA_SASL_PASSWORD",
        "KAFKA_SSL_CA_LOCATION",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    values = runpy.run_path(str(Path(__file__).resolve().parents[2] / "config/settings/base.py"))
    assert [values[name] for name in names] == ["PLAINTEXT", "PLAIN", "", "", ""]


def test_settings_read_kafka_environment(monkeypatch):
    expected = {
        "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
        "KAFKA_SASL_USERNAME": "test-user",
        "KAFKA_SASL_PASSWORD": "test-password",
        "KAFKA_SSL_CA_LOCATION": "/certs/ca.pem",
    }
    for name, value in expected.items():
        monkeypatch.setenv(name, value)
    values = runpy.run_path(str(Path(__file__).resolve().parents[2] / "config/settings/base.py"))
    assert {name: values[name] for name in expected} == expected


def test_connection_defaults_to_plaintext():
    assert kafka.kafka_connection_config() == {
        "bootstrap.servers": "isolated-broker.test:9092",
        "security.protocol": "PLAINTEXT",
    }


@pytest.mark.parametrize("protocol", ["PLAINTEXT", "SSL"])
def test_non_sasl_does_not_include_unused_credentials(kafka_settings, protocol):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = protocol
    kafka_settings.KAFKA_SASL_MECHANISM = "unused"
    kafka_settings.KAFKA_SASL_USERNAME = "test-user"
    kafka_settings.KAFKA_SASL_PASSWORD = "test-password"
    assert kafka.kafka_connection_config() == {
        "bootstrap.servers": "isolated-broker.test:9092",
        "security.protocol": protocol,
    }


@pytest.mark.parametrize("protocol", ["SASL_SSL", "SASL_PLAINTEXT"])
@pytest.mark.parametrize("mechanism", ["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"])
def test_sasl_includes_supported_authentication(kafka_settings, protocol, mechanism):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = protocol
    kafka_settings.KAFKA_SASL_MECHANISM = mechanism
    kafka_settings.KAFKA_SASL_USERNAME = "test-user"
    kafka_settings.KAFKA_SASL_PASSWORD = " test-password "
    assert kafka.kafka_connection_config() == {
        "bootstrap.servers": "isolated-broker.test:9092",
        "security.protocol": protocol,
        "sasl.mechanism": mechanism,
        "sasl.username": "test-user",
        "sasl.password": " test-password ",
    }


@pytest.mark.parametrize("protocol", ["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"])
def test_custom_ca_only_applies_to_tls(kafka_settings, protocol):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = protocol
    kafka_settings.KAFKA_SASL_USERNAME = "test-user"
    kafka_settings.KAFKA_SASL_PASSWORD = "test-password"
    kafka_settings.KAFKA_SSL_CA_LOCATION = "/certs/ca.pem"
    config = kafka.kafka_connection_config()
    assert config.get("ssl.ca.location") == (
        "/certs/ca.pem" if protocol in {"SSL", "SASL_SSL"} else None
    )


def test_protocol_and_mechanism_are_normalized(kafka_settings):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = " sasl_ssl "
    kafka_settings.KAFKA_SASL_MECHANISM = " scram-sha-256 "
    kafka_settings.KAFKA_SASL_USERNAME = "test-user"
    kafka_settings.KAFKA_SASL_PASSWORD = "test-password"
    config = kafka.kafka_connection_config()
    assert config["security.protocol"] == "SASL_SSL"
    assert config["sasl.mechanism"] == "SCRAM-SHA-256"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KAFKA_SECURITY_PROTOCOL", "invalid-secret-protocol"),
        ("KAFKA_SECURITY_PROTOCOL", ""),
        ("KAFKA_SASL_MECHANISM", "invalid-secret-mechanism"),
        ("KAFKA_SASL_USERNAME", ""),
        ("KAFKA_SASL_PASSWORD", ""),
    ],
)
def test_invalid_configuration_fails_without_exposing_values(kafka_settings, name, value):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    kafka_settings.KAFKA_SASL_USERNAME = "secret-user"
    kafka_settings.KAFKA_SASL_PASSWORD = "secret-password"
    setattr(kafka_settings, name, value)
    with pytest.raises(ImproperlyConfigured, match=name) as error:
        kafka.kafka_connection_config()
    for sensitive in ("secret-user", "secret-password", value):
        if sensitive:
            assert sensitive not in str(error.value)


def test_every_client_receives_connection_options_and_keeps_delivery_guards(
    monkeypatch, kafka_settings
):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    kafka_settings.KAFKA_SASL_MECHANISM = "SCRAM-SHA-512"
    kafka_settings.KAFKA_SASL_USERNAME = "test-user"
    kafka_settings.KAFKA_SASL_PASSWORD = "test-password"
    kafka_settings.KAFKA_SSL_CA_LOCATION = "/certs/ca.pem"
    publisher = Mock()
    dlq = Mock()
    consumer_driver = Mock()
    consumer_driver.poll.side_effect = KeyboardInterrupt
    consumer = Mock(return_value=consumer_driver)
    monkeypatch.setattr(kafka, "Producer", publisher)
    monkeypatch.setattr(consume_work, "Producer", dlq)
    monkeypatch.setattr(consume_work, "Consumer", consumer)

    kafka.KafkaPublisher()
    consume_work.Command().handle()

    connection = kafka.kafka_connection_config()
    producer_options = {**connection, "enable.idempotence": True, "message.timeout.ms": 10000}
    publisher.assert_called_once_with(producer_options)
    dlq.assert_called_once_with(producer_options)
    consumer.assert_called_once_with(
        {
            **connection,
            "group.id": kafka_settings.WORK_KAFKA_GROUP,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        }
    )
    consumer_driver.subscribe.assert_called_once_with([kafka_settings.WORK_KAFKA_TOPIC])
    consumer_driver.close.assert_called_once_with()


@pytest.mark.parametrize(
    "client",
    [kafka.KafkaPublisher, consume_work.DeadLetterPublisher, consume_work.Command().handle],
)
def test_invalid_config_fails_before_constructing_clients(monkeypatch, kafka_settings, client):
    kafka_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    producer = Mock()
    consumer = Mock()
    monkeypatch.setattr(kafka, "Producer", producer)
    monkeypatch.setattr(consume_work, "Producer", producer)
    monkeypatch.setattr(consume_work, "Consumer", consumer)
    with pytest.raises(ImproperlyConfigured, match="KAFKA_SASL_USERNAME"):
        client()
    producer.assert_not_called()
    consumer.assert_not_called()
