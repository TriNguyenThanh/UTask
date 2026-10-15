from importlib import import_module

from django.db import migrations

previous = import_module("apps.collaboration.migrations.0002_subject_guards").SQL.split(
    "CREATE TRIGGER"
)[0]
SQL = (
    previous.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    .replace(
        "  IF TG_TABLE_NAME='comments' AND ROW(NEW.user_id,NEW.is_teacher_feedback)",
        "  IF TG_TABLE_NAME='comments' THEN\n    IF ROW(NEW.user_id,NEW.is_teacher_feedback)",
    )
    .replace(
        "  ELSIF TG_TABLE_NAME='attachments' THEN",
        "    END IF;\n  ELSIF TG_TABLE_NAME='attachments' THEN",
    )
)


class Migration(migrations.Migration):
    dependencies = [("collaboration", "0002_subject_guards")]
    operations = [
        migrations.RunSQL(SQL, previous.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    ]
