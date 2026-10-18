from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("courses", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="course",
            name="created_by_id",
            field=models.UUIDField(editable=False, null=True),
        ),
    ]
