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

: "${IDENTITY_DB_NAME:?Missing IDENTITY_DB_NAME}"
: "${WORK_DB_NAME:?Missing WORK_DB_NAME}"
: "${CLASSROOM_DB_NAME:?Missing CLASSROOM_DB_NAME}"
: "${INTEGRATION_DB_NAME:?Missing INTEGRATION_DB_NAME}"
: "${NOTIFICATION_DB_NAME:?Missing NOTIFICATION_DB_NAME}"
: "${AI_DB_NAME:?Missing AI_DB_NAME}"

create_database "$IDENTITY_DB_NAME"
create_database "$WORK_DB_NAME"
create_database "$CLASSROOM_DB_NAME"
create_database "$INTEGRATION_DB_NAME"
create_database "$NOTIFICATION_DB_NAME"
create_database "$AI_DB_NAME"

# Notification uses a dedicated, non-admin login. Leave disabled services alone.
if [ -n "${NOTIFICATION_DB_PASSWORD:-}" ]; then
  : "${NOTIFICATION_DB_USER:?Set NOTIFICATION_DB_USER with NOTIFICATION_DB_PASSWORD}"
  if [ "$NOTIFICATION_DB_USER" = "$POSTGRES_USER" ]; then
    echo 'Notification database login must differ from the PostgreSQL administrator.' >&2
    exit 1
  fi
  export NOTIFICATION_DB_USER NOTIFICATION_DB_PASSWORD NOTIFICATION_DB_NAME
  export IDENTITY_DB_NAME WORK_DB_NAME CLASSROOM_DB_NAME INTEGRATION_DB_NAME AI_DB_NAME POSTGRES_DB
  psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv notification_user NOTIFICATION_DB_USER
\getenv notification_password NOTIFICATION_DB_PASSWORD
\getenv notification_database NOTIFICATION_DB_NAME
SELECT format('CREATE ROLE %I', :'notification_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'notification_user')
\gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'notification_user', :'notification_password')
\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'notification_database', :'notification_user')
\gexec
-- Restrict managed databases only; retain explicit grants and owner access.
\getenv identity_database IDENTITY_DB_NAME
\getenv work_database WORK_DB_NAME
\getenv classroom_database CLASSROOM_DB_NAME
\getenv integration_database INTEGRATION_DB_NAME
\getenv ai_database AI_DB_NAME
\getenv administrator_database POSTGRES_DB
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', datname)
FROM pg_database WHERE datname IN (
  :'identity_database', :'work_database', :'classroom_database',
  :'integration_database', :'ai_database', :'notification_database',
  :'administrator_database', 'postgres', 'template1'
)
\gexec
SQL
  psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$NOTIFICATION_DB_NAME" <<'SQL'
\getenv notification_user NOTIFICATION_DB_USER
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('ALTER SCHEMA public OWNER TO %I', :'notification_user')
\gexec
SQL
fi
