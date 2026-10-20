from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.core.exceptions import ImproperlyConfigured

from apps.github_connections import outbox, publisher
from apps.github_connections.publisher import build_producer_config, publish_outbox

pytestmark = pytest.mark.unit


def test_plaintext_config_enforces_idempotence_and_all_acks():
    config = build_producer_config({"bootstrap.servers": "broker:9092"})
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["max.in.flight.requests.per.connection"] <= 5
    assert config["log_level"] == 0


def test_sasl_ssl_configuration_and_client_certificates(tmp_path):
    certificate = tmp_path / "certificate.pem"
    certificate.write_text("test-certificate")
    config = build_producer_config(
        {
            "bootstrap.servers": "broker:9093",
            "security.protocol": "SASL_SSL",
            "sasl.mechanism": "SCRAM-SHA-512",
            "sasl.username": "fixture-user",
            "sasl.password": "fixture-secret",
            "ssl.ca.location": str(certificate),
            "ssl.certificate.location": str(certificate),
            "ssl.key.location": str(certificate),
        }
    )
    assert config["sasl.password"] == "fixture-secret"
    assert config["security.protocol"] == "SASL_SSL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"bootstrap.servers": ""},
        {"security.protocol": "INVALID"},
        {"security.protocol": "SASL_SSL"},
        {"security.protocol": "SASL_SSL", "sasl.mechanism": "GSSAPI"},
        {"sasl.password": "fixture-secret"},
        {"security.protocol": "SSL", "ssl.ca.location": "/missing/fixture-secret"},
        {"ssl.ca.location": "/missing/fixture-secret"},
        {"enable.idempotence": False},
    ],
)
def test_invalid_config_fails_closed_without_echoing_secret(overrides):
    with pytest.raises(ImproperlyConfigured) as exc:
        build_producer_config({"bootstrap.servers": "broker:9092", **overrides})
    assert "fixture-secret" not in str(exc.value)


def test_client_certificate_requires_paired_key(tmp_path):
    certificate = tmp_path / "certificate.pem"
    certificate.touch()
    with pytest.raises(ImproperlyConfigured, match="must pair"):
        build_producer_config(
            {
                "bootstrap.servers": "broker:9093",
                "security.protocol": "SSL",
                "ssl.certificate.location": str(certificate),
            }
        )


def test_disabled_publisher_does_not_open_broker_or_database(settings):
    settings.INTEGRATION_KAFKA_ENABLED = False
    producer = Mock()
    assert publish_outbox(producer_factory=producer) == 0
    producer.assert_not_called()


@pytest.mark.parametrize("batch_size", [0, -1, True, "100"])
def test_publisher_rejects_invalid_batch_size(batch_size):
    with pytest.raises(ValueError, match="positive integer"):
        publish_outbox(batch_size=batch_size)


@pytest.fixture
def publication(monkeypatch, settings):
    settings.INTEGRATION_KAFKA_ENABLED = True
    settings.INTEGRATION_KAFKA = {"bootstrap.servers": "fixture:9092"}
    clock = [0.0]
    monkeypatch.setattr(publisher.time, "monotonic", lambda: clock[0])
    event = SimpleNamespace(project_id="project", event_id="event", lease_id="lease", envelope={})
    claim = Mock(side_effect=[[event], []])
    complete, retry = Mock(return_value=1), Mock(return_value=1)
    monkeypatch.setattr(outbox, "claim_outbox", claim)
    monkeypatch.setattr(outbox, "complete_event", complete)
    monkeypatch.setattr(outbox, "retry_event", retry)

    def database_operation(operation, *, deadline, **kwargs):
        if deadline - clock[0] <= 6:
            raise TimeoutError
        return operation(**kwargs)

    # Also works against the old publisher, which ignores this seam: regressions fail there.
    monkeypatch.setattr(publisher, "run_database_operation", database_operation, raising=False)
    producer = Mock()

    def flush(timeout):
        clock[0] += timeout
        producer.produce.call_args.kwargs["on_delivery"](None, None)
        return 0

    producer.flush.side_effect = flush
    return SimpleNamespace(
        clock=clock,
        event=event,
        claim=claim,
        complete=complete,
        retry=retry,
        producer=producer,
        factory=Mock(return_value=producer),
    )


@pytest.mark.parametrize("claim_seconds,returns_pending", [(28, True), (31, False)])
def test_slow_claim_never_sends_without_cleanup_budget(publication, claim_seconds, returns_pending):
    p = publication

    def claim(**kwargs):
        p.clock[0] += claim_seconds
        return [p.event]

    p.claim.side_effect = claim
    assert publish_outbox(producer_factory=p.factory) == 0
    p.factory.assert_not_called()
    assert p.retry.called is returns_pending
    p.complete.assert_not_called()
    assert p.clock[0] < 40


def test_broker_timeout_accounts_for_claim_and_leaves_database_reserve(publication):
    p = publication

    def claim(**kwargs):
        p.clock[0] += 10
        return [p.event]

    p.claim.side_effect = claim
    assert publish_outbox(batch_size=1, producer_factory=p.factory) == 1
    timeout = p.producer.flush.call_args.args[0]
    assert 0 < timeout <= 15
    assert p.clock[0] <= 25
    p.complete.assert_called_once()


def test_producer_startup_is_rechecked_before_sending(publication):
    p = publication

    def factory(config):
        p.clock[0] += 28
        return p.producer

    assert publish_outbox(producer_factory=factory) == 0
    p.producer.produce.assert_not_called()
    p.retry.assert_called_once()


def test_produce_time_is_deducted_from_flush_budget(publication):
    p = publication
    p.producer.produce.side_effect = lambda *args, **kwargs: p.clock.__setitem__(0, 5)
    assert publish_outbox(batch_size=1, producer_factory=p.factory) == 1
    assert p.producer.flush.call_args.args[0] <= 20


@pytest.mark.parametrize("stage", ["claim", "produce", "flush", "complete", "retry"])
def test_soft_timeout_propagates_without_sending_another_event(publication, stage):
    p = publication
    target = {
        "claim": p.claim,
        "produce": p.producer.produce,
        "flush": p.producer.flush,
        "complete": p.complete,
        "retry": p.retry,
    }[stage]
    target.side_effect = SoftTimeLimitExceeded()
    if stage == "retry":
        p.producer.flush.side_effect = RuntimeError("fixture-secret")
    with pytest.raises(SoftTimeLimitExceeded):
        publish_outbox(producer_factory=p.factory)
    assert p.claim.call_count == 1
    if stage in {"produce", "flush", "complete"}:
        p.retry.assert_not_called()


def test_slow_completion_does_not_start_another_claim(publication):
    p = publication

    def complete(**kwargs):
        p.clock[0] += 8
        return 1

    p.complete.side_effect = complete
    assert publish_outbox(producer_factory=p.factory) == 1
    assert p.clock[0] <= 35
    assert p.claim.call_count == 1
