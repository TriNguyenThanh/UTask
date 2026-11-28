"""Write guard enforcing append-only immutability on work_activities."""

from django.db import migrations

SQL = """
CREATE FUNCTION work_activity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Activity is append only' USING ERRCODE='23514',
    CONSTRAINT='chk_activity_append_only';
END $$;
CREATE TRIGGER work_activity_immutable BEFORE UPDATE OR DELETE ON work_activities
  FOR EACH ROW EXECUTE FUNCTION work_activity_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS work_activity_immutable ON work_activities;
DROP FUNCTION IF EXISTS work_activity_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("activities", "0001_initial"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
