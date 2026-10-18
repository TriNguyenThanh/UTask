#!/bin/sh
set -eu

: "${POSTGRES_USER:?Missing POSTGRES_USER}"
: "${POSTGRES_DB:?Missing POSTGRES_DB}"
: "${IDENTITY_DB_NAME:?Missing IDENTITY_DB_NAME}"
: "${WORK_DB_NAME:?Missing WORK_DB_NAME}"
: "${CLASSROOM_DB_NAME:?Missing CLASSROOM_DB_NAME}"
: "${INTEGRATION_DB_NAME:?Missing INTEGRATION_DB_NAME}"
: "${NOTIFICATION_DB_NAME:?Missing NOTIFICATION_DB_NAME}"
: "${INTEGRATION_DB_USER:?Missing INTEGRATION_DB_USER}"
: "${INTEGRATION_DB_PASSWORD:?Missing INTEGRATION_DB_PASSWORD}"

# Reject collisions before executing SQL, including PostgreSQL identifier truncation.
validate_identifier() {
  if [ "$(LC_ALL=C printf '%s' "$1" | wc -c)" -gt 63 ]; then
    echo 'PostgreSQL identifiers must fit in 63 bytes.' >&2
    exit 1
  fi
  case "$1" in
    *'='*|*'
'*) echo 'Unsupported PostgreSQL identifier.' >&2; exit 1 ;;
  esac
}
validate_identifier "$INTEGRATION_DB_USER"
case "$INTEGRATION_DB_USER" in
  "$POSTGRES_USER"|pg_*|PUBLIC|public)
    echo 'Integration database role collides with an administrative role.' >&2
    exit 1 ;;
esac
for database_name in "$IDENTITY_DB_NAME" "$WORK_DB_NAME" "$CLASSROOM_DB_NAME" "$INTEGRATION_DB_NAME" "$NOTIFICATION_DB_NAME"; do
  validate_identifier "$database_name"
  case "$database_name" in
    "$POSTGRES_DB"|postgres|template0|template1)
      echo 'Service database collides with an administrative database.' >&2
      exit 1 ;;
  esac
  count=0
  for candidate in "$IDENTITY_DB_NAME" "$WORK_DB_NAME" "$CLASSROOM_DB_NAME" "$INTEGRATION_DB_NAME" "$NOTIFICATION_DB_NAME"; do
    if [ "$database_name" = "$candidate" ]; then count=$((count + 1)); fi
  done
  if [ "$count" -ne 1 ]; then
    echo 'Service database names must be distinct.' >&2
    exit 1
  fi
done

# A reused role must already be a dedicated, unprivileged Integration login.
psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv integration_role INTEGRATION_DB_USER
\getenv integration_database INTEGRATION_DB_NAME
\getenv shared_owner POSTGRES_USER
SELECT EXISTS (
  SELECT 1 FROM pg_roles r WHERE r.rolname = :'integration_role'
    AND (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls
      OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid OR m.roleid = r.oid)
      OR EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba = r.oid AND d.datname <> :'integration_database'))
) OR EXISTS (
  SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba
  WHERE d.datname = :'integration_database' AND r.rolname NOT IN (:'integration_role', :'shared_owner')
) AS unsafe_role \gset
\if :unsafe_role
  \echo 'Existing Integration role/database has conflicting ownership or privileges.'
  SELECT CAST('Unsafe Integration role/database collision' AS integer);
\endif
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT', :'integration_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'integration_role')
\gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT', :'integration_role')
\gexec
SQL

create_database() {
  database_name="$1"
  psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database_name="$database_name" <<'SQL'
SELECT format('CREATE DATABASE %I', :'database_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')
\gexec
SQL
}

create_database "$IDENTITY_DB_NAME"
create_database "$WORK_DB_NAME"
create_database "$CLASSROOM_DB_NAME"
create_database "$INTEGRATION_DB_NAME"
create_database "$NOTIFICATION_DB_NAME"

# PUBLIC grants are additive: a REVOKE from just Integration cannot deny CONNECT.
# Limit changes to managed databases plus PostgreSQL's default connection databases.
for database_name in "$IDENTITY_DB_NAME" "$WORK_DB_NAME" "$CLASSROOM_DB_NAME" "$INTEGRATION_DB_NAME" "$NOTIFICATION_DB_NAME" "$POSTGRES_DB" postgres template1; do
  psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database_name="$database_name" <<'SQL'
\getenv integration_role INTEGRATION_DB_USER
\getenv shared_owner POSTGRES_USER
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', :'database_name')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'database_name', :'integration_role')
\gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'database_name', :'shared_owner')
\gexec
SQL
done

psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$INTEGRATION_DB_NAME" <<'SQL'
\getenv integration_role INTEGRATION_DB_USER
\getenv integration_database INTEGRATION_DB_NAME
SELECT format('ALTER DATABASE %I OWNER TO %I', :'integration_database', :'integration_role')
\gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'integration_database', :'integration_role')
\gexec
ALTER SCHEMA public OWNER TO :"integration_role";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL

# Read the secret from the process environment, never argv or generated files.
# Hide SQL errors in this phase; PostgreSQL otherwise includes failed statements.
if psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" 2>/dev/null <<'SQL'
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
\getenv integration_role INTEGRATION_DB_USER
\getenv integration_password INTEGRATION_DB_PASSWORD
SELECT format('ALTER ROLE %I PASSWORD %L', :'integration_role', :'integration_password')
\gexec
SQL
then
  :
else
  echo 'Integration PostgreSQL credential preparation failed.' >&2
  exit 1
fi
