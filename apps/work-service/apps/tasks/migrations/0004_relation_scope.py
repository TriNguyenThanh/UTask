from django.db import migrations

SQL = """
CREATE FUNCTION work_relation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM tasks a JOIN tasks b ON a.project_id=b.project_id
    WHERE a.id=NEW.task_id AND b.id=NEW.related_task_id) THEN
    RAISE EXCEPTION 'Relation scope mismatch' USING ERRCODE='23514',
      CONSTRAINT='chk_relation_scope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_relation_scope BEFORE INSERT OR UPDATE ON task_relations
FOR EACH ROW EXECUTE FUNCTION work_relation_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("tasks", "0003_taskrelation")]
    operations = [
        migrations.RunSQL(
            SQL,
            "DROP TRIGGER work_relation_scope ON task_relations; "
            "DROP FUNCTION work_relation_guard();",
        )
    ]
