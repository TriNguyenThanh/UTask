import os

from django.core.exceptions import ImproperlyConfigured


def required_environment(name):
    value = os.environ.get(name, "")
    if not value.strip():
        raise ImproperlyConfigured(f"{name} is required")
    return value


def parse_allowed_hosts(value):
    hosts = [host.strip() for host in value.split(",") if host.strip()]
    if not hosts or "*" in hosts:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS requires explicit hosts")
    return hosts


def parse_database_port(value, name="POSTGRES_PORT"):
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{name} must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ImproperlyConfigured(f"{name} must be an integer between 1 and 65535")
    return str(port)
