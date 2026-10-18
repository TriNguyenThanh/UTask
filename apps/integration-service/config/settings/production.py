from common.configuration import parse_allowed_hosts, parse_database_port, required_environment

from .base import *  # noqa: F403

SECRET_KEY = required_environment("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = parse_allowed_hosts(required_environment("DJANGO_ALLOWED_HOSTS"))
DATABASES["default"].update(  # noqa: F405
    NAME=required_environment("DATABASE_NAME"),
    USER=required_environment("INTEGRATION_DB_USER"),
    PASSWORD=required_environment("INTEGRATION_DB_PASSWORD"),
    HOST=required_environment("POSTGRES_HOST"),
    PORT=parse_database_port(required_environment("POSTGRES_PORT")),
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
