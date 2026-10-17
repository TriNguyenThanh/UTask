#!/bin/sh
set -eu

# Only the HTTP process applies migrations; workers and management commands skip it.
case "${1:-}" in
    gunicorn|*/gunicorn)
        "${1%gunicorn}python" manage.py migrate --noinput
        ;;
esac

exec "$@"
