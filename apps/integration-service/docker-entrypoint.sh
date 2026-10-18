#!/bin/sh
set -eu

# Only the HTTP process applies migrations; other commands skip this step.
case "${1:-}" in
    gunicorn|*/gunicorn)
        "${1%gunicorn}python" manage.py migrate --noinput
        ;;
esac

exec "$@"
