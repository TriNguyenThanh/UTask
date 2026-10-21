from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("integrations", "0003_githubconnectionoperation")]
    operations = [
        migrations.RunSQL(
            """
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
        """,
            """
        DROP TRIGGER work_connection_operation_guard ON github_connection_operations;
        DROP FUNCTION work_connection_operation_guard();
        """,
        )
    ]
