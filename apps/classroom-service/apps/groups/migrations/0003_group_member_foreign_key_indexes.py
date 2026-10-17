from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("groups", "0002_same_class_foreign_keys")]

    operations = [
        migrations.AddIndex(
            model_name="groupmember",
            index=models.Index(
                fields=["class_section", "group"], name="ix_group_members_class_group"
            ),
        ),
        migrations.AddIndex(
            model_name="groupmember",
            index=models.Index(
                fields=["class_section", "enrollment"], name="ix_group_members_class_enroll"
            ),
        ),
    ]
