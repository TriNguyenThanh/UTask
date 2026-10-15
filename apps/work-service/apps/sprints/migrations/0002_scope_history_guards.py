from django.db import migrations

SQL = """
CREATE FUNCTION work_sprint_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id, NEW.project_id, NEW.created_at) IS DISTINCT FROM
     ROW(OLD.id, OLD.project_id, OLD.created_at) THEN
    RAISE EXCEPTION 'Immutable Sprint ownership' USING ERRCODE='23514';
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION 'Immutable Sprint start' USING ERRCODE='23514';
  END IF;
  IF OLD.status='COMPLETED' AND ROW(NEW.status,NEW.closed_at,NEW.closure_snapshot,NEW.version,
      NEW.name,NEW.goal,NEW.start_date,NEW.end_date,NEW.sort_order) IS DISTINCT FROM
      ROW(OLD.status,OLD.closed_at,OLD.closure_snapshot,OLD.version,
      OLD.name,OLD.goal,OLD.start_date,OLD.end_date,OLD.sort_order) THEN
    RAISE EXCEPTION 'Immutable closed Sprint' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_sprint_guard BEFORE UPDATE ON sprints
  FOR EACH ROW EXECUTE FUNCTION work_sprint_guard();
CREATE FUNCTION work_sprint_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sprint_project uuid; task_project uuid; sprint_status text;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'Scope history cannot be deleted' USING ERRCODE='23514';
  END IF;
  SELECT project_id,status INTO sprint_project,sprint_status FROM sprints WHERE id=NEW.sprint_id;
  SELECT project_id INTO task_project FROM tasks WHERE id=NEW.task_id;
  IF sprint_project IS DISTINCT FROM task_project THEN
    RAISE EXCEPTION 'Scope must share Project' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' AND sprint_status='COMPLETED' THEN
    RAISE EXCEPTION 'Closed scope is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' AND sprint_status='ACTIVE' AND
      NULLIF(btrim(NEW.scope_change_reason),'') IS NULL THEN
    RAISE EXCEPTION 'Active ADD requires reason' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' THEN
    IF ROW(NEW.id,NEW.sprint_id,NEW.task_id,NEW.added_at,NEW.scope_change_reason) IS DISTINCT FROM
       ROW(OLD.id,OLD.sprint_id,OLD.task_id,OLD.added_at,OLD.scope_change_reason) THEN
      RAISE EXCEPTION 'Immutable scope identity/add reason' USING ERRCODE='23514';
    END IF;
    IF OLD.ended_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
      RAISE EXCEPTION 'Ended scope is immutable' USING ERRCODE='23514';
    END IF;
    IF NEW.end_reason='REMOVED' AND sprint_status='ACTIVE' AND
        NULLIF(btrim(NEW.removal_reason),'') IS NULL THEN
      RAISE EXCEPTION 'Active REMOVE requires reason' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_sprint_scope_guard BEFORE INSERT OR UPDATE OR DELETE ON sprint_tasks
  FOR EACH ROW EXECUTE FUNCTION work_sprint_scope_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("sprints", "0001_initial"),
        ("messaging", "0009_activity_sprint_activity_chk_activity_subject"),
    ]
    operations = [
        migrations.RunSQL(
            SQL,
            """
        DROP TRIGGER work_sprint_scope_guard ON sprint_tasks;
        DROP TRIGGER work_sprint_guard ON sprints;
        DROP FUNCTION work_sprint_scope_guard();
        DROP FUNCTION work_sprint_guard();
    """,
        )
    ]
