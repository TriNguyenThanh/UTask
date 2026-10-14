from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("messaging", "0006_remove_activity_chk_activity_subject_and_more")]
    operations = [
        migrations.RunSQL(
            """
CREATE INDEX ix_deadline_task_events
ON outbox_events(project_id,aggregate_id,project_sequence)
WHERE aggregate_type='task';
""",
            "DROP INDEX ix_deadline_task_events;",
        )
    ]
