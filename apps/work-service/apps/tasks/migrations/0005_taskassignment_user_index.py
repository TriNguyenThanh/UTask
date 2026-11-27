from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0004_relation_scope"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="taskassignment",
            index=models.Index(fields=["user_id", "task"], name="ix_task_assignment_user"),
        ),
    ]
