from django.db import migrations

SQL = """
CREATE FUNCTION work_collaboration_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id,NEW.project_id,NEW.task_id,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.task_id,OLD.created_at) THEN
    RAISE EXCEPTION 'Immutable collaboration subject' USING ERRCODE='23514',
    CONSTRAINT='chk_collaboration_identity';
  END IF;
  IF TG_TABLE_NAME='comments' AND ROW(NEW.user_id,NEW.is_teacher_feedback)
    IS DISTINCT FROM ROW(OLD.user_id,OLD.is_teacher_feedback) THEN
    RAISE EXCEPTION 'Immutable author' USING ERRCODE='23514',
    CONSTRAINT='chk_collaboration_identity';
  ELSIF TG_TABLE_NAME='attachments' THEN
    IF ROW(NEW.uploaded_by_user_id,NEW.storage_key,NEW.file_name,NEW.file_size,
       NEW.content_type,NEW.expires_at)
      IS DISTINCT FROM ROW(OLD.uploaded_by_user_id,OLD.storage_key,OLD.file_name,
       OLD.file_size,OLD.content_type,OLD.expires_at) THEN
      RAISE EXCEPTION 'Immutable upload allocation' USING ERRCODE='23514',
      CONSTRAINT='chk_collaboration_identity';
    END IF;
    IF OLD.status<>'PENDING' AND ROW(NEW.status,NEW.confirmed_at)
      IS DISTINCT FROM ROW(OLD.status,OLD.confirmed_at) THEN
      RAISE EXCEPTION 'Immutable confirmed/expired upload' USING ERRCODE='23514',
      CONSTRAINT='chk_attachment_terminal';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_comment_identity BEFORE UPDATE ON comments
FOR EACH ROW EXECUTE FUNCTION work_collaboration_guard();
CREATE TRIGGER work_attachment_identity BEFORE UPDATE ON attachments
FOR EACH ROW EXECUTE FUNCTION work_collaboration_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("collaboration", "0001_initial")]
    operations = [
        migrations.RunSQL(
            SQL,
            """
DROP TRIGGER work_comment_identity ON comments;
DROP TRIGGER work_attachment_identity ON attachments;
DROP FUNCTION work_collaboration_guard();
""",
        )
    ]
