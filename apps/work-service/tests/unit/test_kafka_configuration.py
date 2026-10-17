import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.messaging.management.commands import consume_identity
from infrastructure.kafka.client import KafkaPublisher
from infrastructure.kafka.configuration import kafka_connection_config

pytestmark = pytest.mark.unit


@pytest.fixture
def connection_settings(settings):
    settings.KAFKA_BOOTSTRAP_SERVERS = "broker.example:9092"
    settings.KAFKA_SECURITY_PROTOCOL = "PLAINTEXT"
    settings.KAFKA_SASL_MECHANISM = "PLAIN"
    settings.KAFKA_SASL_USERNAME = "test-user"
    settings.KAFKA_SASL_PASSWORD = " test-password "
    settings.KAFKA_SSL_CA_LOCATION = ""
    return settings


def test_plaintext_connection_omits_unused_credentials_and_ca(connection_settings):
    connection_settings.KAFKA_SSL_CA_LOCATION = "/unused/ca.pem"
    assert kafka_connection_config() == {
        "bootstrap.servers": "broker.example:9092",
        "security.protocol": "PLAINTEXT",
    }


@pytest.mark.parametrize("protocol", ["SASL_SSL", "SASL_PLAINTEXT"])
@pytest.mark.parametrize("mechanism", ["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"])
def test_authenticated_connection_maps_credentials(connection_settings, protocol, mechanism):
    connection_settings.KAFKA_SECURITY_PROTOCOL = protocol.lower()
    connection_settings.KAFKA_SASL_MECHANISM = mechanism.lower()
    assert kafka_connection_config() == {
        "bootstrap.servers": "broker.example:9092",
        "security.protocol": protocol,
        "sasl.mechanism": mechanism,
        "sasl.username": "test-user",
        "sasl.password": " test-password ",
    }


@pytest.mark.parametrize("protocol", ["SSL", "SASL_SSL"])
def test_encrypted_connection_accepts_optional_ca_path(connection_settings, protocol):
    connection_settings.KAFKA_SECURITY_PROTOCOL = protocol
    assert "ssl.ca.location" not in kafka_connection_config()
    connection_settings.KAFKA_SSL_CA_LOCATION = "/certificates/kafka-ca.pem"
    config = kafka_connection_config()
    assert config["ssl.ca.location"] == "/certificates/kafka-ca.pem"
    if protocol == "SSL":
        assert not any(key.startswith("sasl.") for key in config)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KAFKA_SECURITY_PROTOCOL", "secret-invalid-protocol"),
        ("KAFKA_SECURITY_PROTOCOL", ""),
        ("KAFKA_SASL_MECHANISM", "secret-invalid-mechanism"),
        ("KAFKA_SASL_USERNAME", ""),
        ("KAFKA_SASL_PASSWORD", ""),
    ],
)
def test_invalid_authentication_fails_without_exposing_values(connection_settings, name, value):
    connection_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    setattr(connection_settings, name, value)
    with pytest.raises(ImproperlyConfigured, match=name) as exc:
        kafka_connection_config()
    assert "secret-invalid" not in str(exc.value)
    assert "test-password" not in str(exc.value)


def test_producer_consumer_and_dead_letter_use_same_connection(connection_settings, monkeypatch):
    connection_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    connection_settings.KAFKA_SSL_CA_LOCATION = "/certificates/kafka-ca.pem"
    connection_settings.IDENTITY_KAFKA_TOPIC = "agreed-profile-topic"
    expected = kafka_connection_config()
    event_producer = Mock()
    dead_letter_producer = Mock()
    consumer_factory = Mock()
    consumer_factory.return_value.poll.side_effect = KeyboardInterrupt
    monkeypatch.setattr("infrastructure.kafka.client.Producer", event_producer)
    monkeypatch.setattr(consume_identity, "Producer", dead_letter_producer)
    monkeypatch.setattr(consume_identity, "Consumer", consumer_factory)
    KafkaPublisher()
    consume_identity.Command().handle()
    for factory in [event_producer, dead_letter_producer, consumer_factory]:
        config = factory.call_args.args[0]
        assert all(config[key] == value for key, value in expected.items())
    for factory in [event_producer, dead_letter_producer]:
        assert factory.call_args.args[0]["enable.idempotence"] is True
        assert factory.call_args.args[0]["message.timeout.ms"] == 10000
    consumer_config = consumer_factory.call_args.args[0]
    assert consumer_config["enable.auto.commit"] is False
    assert consumer_config["enable.auto.offset.store"] is False
    consumer_factory.return_value.close.assert_called_once()


@pytest.mark.parametrize(
    "client",
    [KafkaPublisher, consume_identity.DeadLetterPublisher, consume_identity.Command().handle],
)
def test_invalid_credentials_stop_before_creating_clients(connection_settings, monkeypatch, client):
    connection_settings.KAFKA_SECURITY_PROTOCOL = "SASL_SSL"
    connection_settings.KAFKA_SASL_PASSWORD = ""
    connection_settings.IDENTITY_KAFKA_TOPIC = "agreed-profile-topic"
    producer = Mock()
    consumer = Mock()
    monkeypatch.setattr("infrastructure.kafka.client.Producer", producer)
    monkeypatch.setattr(consume_identity, "Producer", producer)
    monkeypatch.setattr(consume_identity, "Consumer", consumer)
    with pytest.raises(ImproperlyConfigured, match="KAFKA_SASL_PASSWORD"):
        client()
    producer.assert_not_called()
    consumer.assert_not_called()


@pytest.mark.parametrize("use_environment", [False, True])
def test_base_settings_use_environment_or_plaintext_defaults(monkeypatch, use_environment):
    expected = {
        "KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512",
        "KAFKA_SASL_USERNAME": "configured-user",
        "KAFKA_SASL_PASSWORD": "configured-password",
        "KAFKA_SSL_CA_LOCATION": "/certificates/ca.pem",
    }
    for name, value in expected.items():
        monkeypatch.delenv(name, raising=False)
        if use_environment:
            monkeypatch.setenv(name, value)
    if not use_environment:
        expected = dict(zip(expected, ["PLAINTEXT", "PLAIN", "", "", ""], strict=True))
    values = runpy.run_path(str(Path(__file__).resolve().parents[2] / "config/settings/base.py"))
    assert {name: values[name] for name in expected} == expected
