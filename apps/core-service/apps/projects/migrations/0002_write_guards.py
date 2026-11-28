"""Write guards protecting immutability of projects, states, and project_members."""

from django.db import migrations

SQL = """
CREATE FUNCTION work_subject_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'Immutable subject identity' USING ERRCODE='23514',
      CONSTRAINT='chk_work_identity';
  END IF;
  IF TG_TABLE_NAME = 'projects' THEN
    IF NEW.identifier IS DISTINCT FROM OLD.identifier
       OR NEW.classroom_group_id IS DISTINCT FROM OLD.classroom_group_id THEN
      RAISE EXCEPTION 'Immutable project ownership' USING ERRCODE='23514',
        CONSTRAINT='chk_work_identity';
    END IF;
  ELSIF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
    RAISE EXCEPTION 'Immutable state ownership' USING ERRCODE='23514',
      CONSTRAINT='chk_work_identity';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_project_identity BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION work_subject_guard();
CREATE TRIGGER work_state_identity BEFORE UPDATE ON states
  FOR EACH ROW EXECUTE FUNCTION work_subject_guard();

CREATE FUNCTION work_member_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.project_id IS DISTINCT FROM OLD.project_id OR
     NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'Immutable membership slot' USING ERRCODE='23514',
      CONSTRAINT='chk_work_identity';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_member_identity BEFORE UPDATE ON project_members
  FOR EACH ROW EXECUTE FUNCTION work_member_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS work_member_identity ON project_members;
DROP TRIGGER IF EXISTS work_state_identity ON states;
DROP TRIGGER IF EXISTS work_project_identity ON projects;
DROP FUNCTION IF EXISTS work_member_guard();
DROP FUNCTION IF EXISTS work_subject_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
