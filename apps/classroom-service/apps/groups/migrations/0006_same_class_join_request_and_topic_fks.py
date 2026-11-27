from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("groups", "0005_open_groups_join_requests_topics"),
        ("courses", "0004_classsection_formation_deadline"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_JOIN_REQUESTS" ADD CONSTRAINT fk_join_request_same_class_group FOREIGN KEY (class_section_id, group_id) REFERENCES "STUDY_GROUPS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_JOIN_REQUESTS" DROP CONSTRAINT fk_join_request_same_class_group',  # noqa: E501
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_JOIN_REQUESTS" ADD CONSTRAINT fk_join_request_same_class_enrollment FOREIGN KEY (class_section_id, enrollment_id) REFERENCES "ENROLLMENTS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_JOIN_REQUESTS" DROP CONSTRAINT fk_join_request_same_class_enrollment',  # noqa: E501
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "GROUP_TOPIC_PROPOSALS" ADD CONSTRAINT fk_topic_proposal_same_class_group FOREIGN KEY (class_section_id, group_id) REFERENCES "STUDY_GROUPS" (class_section_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED',  # noqa: E501
            reverse_sql='ALTER TABLE "GROUP_TOPIC_PROPOSALS" DROP CONSTRAINT fk_topic_proposal_same_class_group',  # noqa: E501
        ),
    ]
