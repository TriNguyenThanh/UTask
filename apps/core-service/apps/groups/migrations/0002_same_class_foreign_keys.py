"""Composite deferrable foreign keys enforcing same-class integrity across group tables."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("groups", "0001_initial"), ("courses", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_members" ADD CONSTRAINT fk_group_member_same_class_group '
                'FOREIGN KEY (class_section_id, group_id) REFERENCES "study_groups" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_members" DROP CONSTRAINT fk_group_member_same_class_group'
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_members" ADD CONSTRAINT fk_group_member_same_class_enrollment '
                'FOREIGN KEY (class_section_id, enrollment_id) REFERENCES "enrollments" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_members" DROP CONSTRAINT fk_group_member_same_class_enrollment'
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_project_links" '
                "ADD CONSTRAINT fk_group_project_same_class_group "
                'FOREIGN KEY (class_section_id, group_id) REFERENCES "study_groups" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_project_links" '
                "DROP CONSTRAINT fk_group_project_same_class_group"
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_join_requests" ADD CONSTRAINT fk_join_request_same_class_group '
                'FOREIGN KEY (class_section_id, group_id) REFERENCES "study_groups" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_join_requests" DROP CONSTRAINT fk_join_request_same_class_group'
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_join_requests" '
                "ADD CONSTRAINT fk_join_request_same_class_enrollment "
                'FOREIGN KEY (class_section_id, enrollment_id) REFERENCES "enrollments" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_join_requests" '
                "DROP CONSTRAINT fk_join_request_same_class_enrollment"
            ),
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "group_topic_proposals" '
                "ADD CONSTRAINT fk_topic_proposal_same_class_group "
                'FOREIGN KEY (class_section_id, group_id) REFERENCES "study_groups" '
                "(class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                'ALTER TABLE "group_topic_proposals" '
                "DROP CONSTRAINT fk_topic_proposal_same_class_group"
            ),
        ),
    ]
