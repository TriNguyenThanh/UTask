#!/bin/sh
set -eu

create_database() {
  database_name="$1"

  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database_name="$database_name" <<'SQL'
SELECT format('CREATE DATABASE %I', :'database_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')
\gexec
SQL
}

: "${IDENTITY_DB_NAME:?Missing IDENTITY_DB_NAME}"
: "${WORK_DB_NAME:?Missing WORK_DB_NAME}"
: "${CLASSROOM_DB_NAME:?Missing CLASSROOM_DB_NAME}"
: "${INTEGRATION_DB_NAME:?Missing INTEGRATION_DB_NAME}"
: "${NOTIFICATION_DB_NAME:?Missing NOTIFICATION_DB_NAME}"

create_database "$IDENTITY_DB_NAME"
create_database "$WORK_DB_NAME"
create_database "$CLASSROOM_DB_NAME"
create_database "$INTEGRATION_DB_NAME"
create_database "$NOTIFICATION_DB_NAME"
