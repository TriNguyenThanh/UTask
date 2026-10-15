from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_initial")]
    operations = [
        migrations.RunSQL(
            """
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
    """,
            """
        DROP TRIGGER work_github_ref_guard ON task_github_links;
        DROP FUNCTION work_github_ref_guard();
    """,
        )
    ]
