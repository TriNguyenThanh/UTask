from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("groups", "0001_initial"), ("courses", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_MEMBERS" ADD CONSTRAINT fk_group_member_same_class_group FOREIGN KEY (class_section_id, group_id) REFERENCES "STUDY_GROUPS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_MEMBERS" DROP CONSTRAINT fk_group_member_same_class_group',  # noqa: E501
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_MEMBERS" ADD CONSTRAINT fk_group_member_same_class_enrollment FOREIGN KEY (class_section_id, enrollment_id) REFERENCES "ENROLLMENTS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_MEMBERS" DROP CONSTRAINT fk_group_member_same_class_enrollment',  # noqa: E501
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_PROJECT_LINKS" ADD CONSTRAINT fk_group_project_same_class_group FOREIGN KEY (class_section_id, group_id) REFERENCES "STUDY_GROUPS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_PROJECT_LINKS" DROP CONSTRAINT fk_group_project_same_class_group',  # noqa: E501
        ),
    ]
