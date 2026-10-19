#!/bin/sh
set -eu

case "${1:-}" in
    uvicorn|*/uvicorn)
        "${1%uvicorn}alembic" upgrade head
        ;;
esac

exec "$@"
