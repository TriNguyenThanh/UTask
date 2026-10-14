from django.db import migrations

SQL = """
CREATE FUNCTION work_task_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_project uuid; target_group text;
BEGIN
  IF TG_OP = 'UPDATE'
    AND ROW(NEW.id,
    NEW.project_id,
    NEW.sequence_id,
    NEW.created_by_user_id,
    NEW.created_at,
    NEW.source,
    NEW.ai_proposal_id,
    NEW.ai_local_id,
    NEW.ai_revision,
    NEW.ai_payload_hash)
    IS DISTINCT FROM ROW(OLD.id,
    OLD.project_id,
    OLD.sequence_id,
    OLD.created_by_user_id,
    OLD.created_at,
    OLD.source,
    OLD.ai_proposal_id,
    OLD.ai_local_id,
    OLD.ai_revision,
    OLD.ai_payload_hash) THEN
    RAISE EXCEPTION 'Immutable Task identity/provenance' USING ERRCODE='23514',
CONSTRAINT='chk_task_identity';
  END IF;
  SELECT project_id, "group" INTO target_project, target_group FROM states
    WHERE id=NEW.state_id;
  IF target_project IS DISTINCT FROM NEW.project_id THEN
    RAISE EXCEPTION 'State scope mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_task_scope';
  END IF;
  IF (target_group='COMPLETED') IS DISTINCT FROM (NEW.completed_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Completion timestamp mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_task_completion';
  END IF;
  IF NEW.epic_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM epics
    WHERE id=NEW.epic_id
    AND project_id=NEW.project_id) THEN
    RAISE EXCEPTION 'Epic scope mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_task_scope';
  END IF;
  IF NEW.parent_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM tasks
    WHERE id=NEW.parent_id
    AND project_id=NEW.project_id) THEN
    RAISE EXCEPTION 'Parent scope mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_task_scope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_task_scope BEFORE INSERT OR UPDATE ON tasks FOR EACH ROW
EXECUTE FUNCTION work_task_guard();
CREATE TRIGGER work_epic_identity BEFORE UPDATE ON epics FOR EACH ROW
EXECUTE FUNCTION work_subject_guard();
CREATE TRIGGER work_label_identity BEFORE UPDATE ON labels FOR EACH ROW
EXECUTE FUNCTION work_subject_guard();
CREATE FUNCTION work_assignment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tasks t JOIN project_members m ON m.project_id=t.project_id
   
    WHERE t.id=NEW.task_id
    AND m.user_id=NEW.user_id
    AND m.status='ACTIVE') THEN
    RAISE EXCEPTION 'Assignee must be an active member' USING ERRCODE='23514',
CONSTRAINT='chk_assignment_scope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_assignment_scope BEFORE INSERT OR UPDATE ON task_assignments FOR EACH ROW
EXECUTE FUNCTION work_assignment_guard();
CREATE FUNCTION work_label_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tasks t JOIN labels l ON t.project_id=l.project_id
    WHERE t.id=NEW.task_id
    AND l.id=NEW.label_id) THEN
    RAISE EXCEPTION 'Label scope mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_task_label_scope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_label_scope BEFORE INSERT OR UPDATE ON task_labels FOR EACH ROW
EXECUTE FUNCTION work_label_link_guard();
"""
REVERSE = """
DROP TRIGGER work_label_scope ON task_labels; DROP FUNCTION work_label_link_guard();
DROP TRIGGER work_assignment_scope ON task_assignments; DROP FUNCTION work_assignment_guard();
DROP TRIGGER work_label_identity ON labels; DROP TRIGGER work_epic_identity ON epics;
DROP TRIGGER work_task_scope ON tasks; DROP FUNCTION work_task_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("tasks", "0001_initial"), ("messaging", "0003_write_guards")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
