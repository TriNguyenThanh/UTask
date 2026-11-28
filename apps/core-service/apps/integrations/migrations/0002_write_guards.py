"""Write guards protecting immutability of GitHub links and connection operations."""

from django.db import migrations

SQL = """
CREATE FUNCTION work_github_ref_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id,NEW.task_id,NEW.github_repo_id,NEW.link_type,NEW.github_ref_id)
    IS DISTINCT FROM ROW(OLD.id,OLD.task_id,OLD.github_repo_id,
      OLD.link_type,OLD.github_ref_id) THEN
    RAISE EXCEPTION 'Immutable GitHub reference ownership' USING ERRCODE='23514';
  END IF;
  IF ROW(NEW.connection_generation,NEW.source_version) <
     ROW(OLD.connection_generation,OLD.source_version) THEN
    RAISE EXCEPTION 'Stale GitHub source facts' USING ERRCODE='23514';
  END IF;
  IF OLD.confirmation_status='CONFIRMED' AND
     ROW(NEW.confirmation_status,NEW.confirmed_by_user_id,NEW.confirmed_at)
     IS DISTINCT FROM
     ROW(OLD.confirmation_status,OLD.confirmed_by_user_id,OLD.confirmed_at) THEN
    RAISE EXCEPTION 'Immutable human confirmation' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_github_ref_guard BEFORE UPDATE ON task_github_links
  FOR EACH ROW EXECUTE FUNCTION work_github_ref_guard();

CREATE FUNCTION work_connection_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id,NEW.project_id,NEW.operation_id,NEW.actor_user_id,
         NEW.action,NEW.payload_hash,NEW.request_body,NEW.created_at)
     IS DISTINCT FROM
     ROW(OLD.id,OLD.project_id,OLD.operation_id,OLD.actor_user_id,
         OLD.action,OLD.payload_hash,OLD.request_body,OLD.created_at) THEN
    RAISE EXCEPTION 'Immutable connection operation identity' USING ERRCODE='23514';
  END IF;
  IF OLD.accepted_at IS NOT NULL AND
     ROW(NEW.accepted_at,NEW.prepared,NEW.generation,NEW.response_data)
     IS DISTINCT FROM
     ROW(OLD.accepted_at,OLD.prepared,OLD.generation,OLD.response_data) THEN
    RAISE EXCEPTION 'Immutable connection receipt' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_connection_operation_guard BEFORE UPDATE ON github_connection_operations
  FOR EACH ROW EXECUTE FUNCTION work_connection_operation_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS work_connection_operation_guard ON github_connection_operations;
DROP FUNCTION IF EXISTS work_connection_operation_guard();
DROP TRIGGER IF EXISTS work_github_ref_guard ON task_github_links;
DROP FUNCTION IF EXISTS work_github_ref_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
