#!/bin/sh
set -eu

create_database() {
  database_name="$1"

  psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database_name="$database_name" <<'SQL'
SELECT format('CREATE DATABASE %I', :'database_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')
\gexec
SQL
}

: "${CORE_DB_NAME:?Missing CORE_DB_NAME}"
: "${INTEGRATION_DB_NAME:?Missing INTEGRATION_DB_NAME}"
: "${NOTIFICATION_DB_NAME:?Missing NOTIFICATION_DB_NAME}"
: "${AI_DB_NAME:?Missing AI_DB_NAME}"

create_database "$CORE_DB_NAME"
create_database "$INTEGRATION_DB_NAME"
create_database "$NOTIFICATION_DB_NAME"
create_database "$AI_DB_NAME"
