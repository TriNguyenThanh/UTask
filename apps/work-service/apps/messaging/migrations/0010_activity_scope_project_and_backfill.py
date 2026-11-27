import django.db.models.deletion
from django.db import migrations, models

BACKFILL_SQL = """
ALTER TABLE activities DISABLE TRIGGER work_activity_immutable;
UPDATE activities a
SET scope_project_id = COALESCE(
    a.project_id,
    (SELECT pm.project_id FROM project_members pm WHERE pm.id = a.project_member_id),
    (SELECT s.project_id FROM states s WHERE s.id = a.state_id),
    (SELECT t.project_id FROM tasks t WHERE t.id = a.task_id),
    (SELECT e.project_id FROM epics e WHERE e.id = a.epic_id),
    (SELECT l.project_id FROM labels l WHERE l.id = a.label_id),
    (SELECT sp.project_id FROM sprints sp WHERE sp.id = a.sprint_id),
    (
        SELECT COALESCE(c.project_id, ct.project_id)
        FROM comments c
        LEFT JOIN tasks ct ON ct.id = c.task_id
        WHERE c.id = a.comment_id
    )
)
WHERE a.scope_project_id IS NULL;
ALTER TABLE activities ENABLE TRIGGER work_activity_immutable;
UPDATE projects p
SET last_activity_at = agg.latest
FROM (
    SELECT scope_project_id, MAX(created_at) AS latest
    FROM activities
    WHERE scope_project_id IS NOT NULL
    GROUP BY scope_project_id
) agg
WHERE p.id = agg.scope_project_id
  AND (p.last_activity_at IS NULL OR p.last_activity_at < agg.latest);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0009_activity_sprint_activity_chk_activity_subject"),
        ("projects", "0003_project_last_activity_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="scope_project",
            field=models.ForeignKey(
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scoped_activities",
                to="projects.project",
            ),
        ),
        migrations.AddIndex(
            model_name="activity",
            index=models.Index(
                fields=["scope_project", "-created_at", "-id"],
                name="ix_activity_scope_project_time",
            ),
        ),
        migrations.RunSQL(BACKFILL_SQL, migrations.RunSQL.noop),
    ]
