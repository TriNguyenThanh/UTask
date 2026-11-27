from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_multiple_group_projects"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="last_activity_at",
            field=models.DateTimeField(null=True),
        ),
    ]
