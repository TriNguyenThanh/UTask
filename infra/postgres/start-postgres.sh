#!/bin/sh
set -eu

# Keep the official entrypoint responsible for fresh-volume initialization.
ready_file=/tmp/utask-postgres-ready
rm -f "$ready_file"
postgres_pid=
postgres_ready=false
preparation_pid=
cleanup() {
  status=$?
  trap - EXIT TERM INT
  rm -f "$ready_file"
  if [ -n "$preparation_pid" ]; then
    kill -TERM "$preparation_pid" 2>/dev/null || :
    wait "$preparation_pid" 2>/dev/null || :
  fi
  if [ -n "$postgres_pid" ]; then
    # The initialization shell may ignore INT; the final server needs fast shutdown.
    if [ "$postgres_ready" = true ]; then
      kill -INT "$postgres_pid" 2>/dev/null || :
    else
      kill -TERM "$postgres_pid" 2>/dev/null || :
    fi
    wait "$postgres_pid" 2>/dev/null || :
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

docker-entrypoint.sh "$@" &
postgres_pid=$!
attempt=0
until pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t 2 >/dev/null 2>&1; do
  if ! kill -0 "$postgres_pid" 2>/dev/null; then
    wait "$postgres_pid" && exit 1 || exit "$?"
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo 'PostgreSQL did not become ready for database preparation.' >&2
    exit 1
  fi
  sleep 1
done
postgres_ready=true

export PGHOST=127.0.0.1 PGPORT="${POSTGRES_PORT:-5432}" PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=5
timeout 60 /bin/sh /docker-entrypoint-initdb.d/init-databases.sh &
preparation_pid=$!
wait "$preparation_pid"
preparation_pid=
kill -0 "$postgres_pid"
touch "$ready_file"
wait "$postgres_pid"
