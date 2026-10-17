from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def kafka_connection_config():
    """Connection options shared by event, consumer and dead-letter clients."""
    protocol = settings.KAFKA_SECURITY_PROTOCOL.strip().upper()
    if protocol not in {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}:
        raise ImproperlyConfigured("KAFKA_SECURITY_PROTOCOL is not supported")
    config = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "security.protocol": protocol,
    }
    if protocol.startswith("SASL_"):
        mechanism = settings.KAFKA_SASL_MECHANISM.strip().upper()
        if mechanism not in {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}:
            raise ImproperlyConfigured("KAFKA_SASL_MECHANISM is not supported")
        if not settings.KAFKA_SASL_USERNAME or not settings.KAFKA_SASL_PASSWORD:
            raise ImproperlyConfigured(
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD are required for SASL"
            )
        config.update(
            {
                "sasl.mechanism": mechanism,
                "sasl.username": settings.KAFKA_SASL_USERNAME,
                "sasl.password": settings.KAFKA_SASL_PASSWORD,
            }
        )
    if protocol in {"SSL", "SASL_SSL"} and settings.KAFKA_SSL_CA_LOCATION:
        config["ssl.ca.location"] = settings.KAFKA_SSL_CA_LOCATION
    return config
