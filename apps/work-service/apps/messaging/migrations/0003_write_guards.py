from django.db import migrations

SQL = """
CREATE FUNCTION work_subject_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'Immutable subject identity' USING ERRCODE='23514',
CONSTRAINT='chk_work_identity';
  END IF;
  IF TG_TABLE_NAME = 'projects' THEN
    IF NEW.identifier IS DISTINCT FROM OLD.identifier OR NEW.classroom_group_id IS DISTINCT FROM
OLD.classroom_group_id THEN
      RAISE EXCEPTION 'Immutable project ownership' USING ERRCODE='23514',
CONSTRAINT='chk_work_identity';
    END IF;
  ELSIF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
    RAISE EXCEPTION 'Immutable state ownership' USING ERRCODE='23514',
CONSTRAINT='chk_work_identity';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_project_identity BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION
work_subject_guard();
CREATE TRIGGER work_state_identity BEFORE UPDATE ON states FOR EACH ROW EXECUTE FUNCTION
work_subject_guard();

CREATE FUNCTION work_member_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.project_id IS DISTINCT FROM OLD.project_id OR
NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'Immutable membership slot' USING ERRCODE='23514',
CONSTRAINT='chk_work_identity';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_member_identity BEFORE UPDATE ON project_members FOR EACH ROW EXECUTE FUNCTION
work_member_guard();

CREATE FUNCTION work_activity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Activity is append only' USING ERRCODE='23514',
CONSTRAINT='chk_activity_append_only';
END $$;
CREATE TRIGGER work_activity_immutable BEFORE UPDATE OR DELETE ON activities FOR EACH ROW EXECUTE
FUNCTION work_activity_guard();

CREATE FUNCTION work_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND ROW(NEW.id, NEW.aggregate_type, NEW.aggregate_id, NEW.event_type,
NEW.event_version, NEW.data, NEW.project_id, NEW.project_sequence, NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id, OLD.aggregate_type, OLD.aggregate_id, OLD.event_type,
OLD.event_version, OLD.data, OLD.project_id, OLD.project_sequence, OLD.created_at) THEN
    RAISE EXCEPTION 'Immutable event envelope' USING ERRCODE='23514',
CONSTRAINT='chk_outbox_immutable';
  END IF;
  IF TG_OP = 'INSERT' AND (
      jsonb_typeof(NEW.data) IS DISTINCT FROM 'object'
      OR NEW.data->>'event_id' IS DISTINCT FROM NEW.id::text
      OR NEW.data->>'event_type' IS DISTINCT FROM NEW.event_type
      OR NEW.data->>'event_version' IS DISTINCT FROM NEW.event_version::text
      OR NEW.data->>'aggregate_id' IS DISTINCT FROM NEW.aggregate_id
      OR NEW.data->>'project_id' IS DISTINCT FROM NEW.project_id::text
      OR NEW.data->>'project_sequence' IS DISTINCT FROM NEW.project_sequence::text
      OR NEW.data->>'producer' IS DISTINCT FROM 'work-service'
      OR (NEW.data->>'occurred_at')::timestamptz IS DISTINCT FROM NEW.created_at
      OR jsonb_typeof(NEW.data->'data') IS DISTINCT FROM 'object'
      OR jsonb_typeof(NEW.data->'entity_version') IS DISTINCT FROM 'number'
  ) THEN
    RAISE EXCEPTION 'Event metadata mismatch' USING ERRCODE='23514',
CONSTRAINT='chk_outbox_envelope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_outbox_immutable BEFORE INSERT OR UPDATE ON outbox_events FOR EACH ROW EXECUTE
FUNCTION work_outbox_guard();

CREATE FUNCTION work_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.response_body->>'success' = 'true' AND ROW(NEW.id, NEW.operation_id, NEW.user_id,
NEW.http_method, NEW.endpoint_path, NEW.idempotency_key, NEW.payload_hash, NEW.ai_proposal_id,
NEW.ai_item_id, NEW.response_status, NEW.response_body, NEW.created_at)
      IS DISTINCT FROM ROW(OLD.id, OLD.operation_id, OLD.user_id, OLD.http_method,
OLD.endpoint_path, OLD.idempotency_key, OLD.payload_hash, OLD.ai_proposal_id, OLD.ai_item_id,
OLD.response_status, OLD.response_body, OLD.created_at) THEN
    RAISE EXCEPTION 'Immutable committed receipt' USING ERRCODE='23514',
CONSTRAINT='chk_receipt_immutable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER work_receipt_immutable BEFORE UPDATE ON idempotency_records FOR EACH ROW EXECUTE
FUNCTION work_receipt_guard();

CREATE FUNCTION work_receipt_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE receipt idempotency_records;
BEGIN
  SELECT * INTO receipt FROM idempotency_records WHERE id=NEW.id;
  IF FOUND AND (receipt.response_status < 200 OR receipt.response_status >= 300
      OR receipt.response_body->>'success' IS DISTINCT FROM 'true'
      OR (SELECT count(*) FROM jsonb_object_keys(receipt.response_body)) != 5
      OR NOT receipt.response_body ?& ARRAY['success','message','data','meta','error']) THEN
    RAISE EXCEPTION 'Incomplete command receipt' USING ERRCODE='23514',
CONSTRAINT='chk_receipt_complete';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER work_receipt_complete AFTER INSERT OR UPDATE ON idempotency_records
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION work_receipt_complete();
"""

REVERSE = """
DROP TRIGGER work_receipt_complete ON idempotency_records;
DROP TRIGGER work_receipt_immutable ON idempotency_records;
DROP TRIGGER work_outbox_immutable ON outbox_events;
DROP TRIGGER work_activity_immutable ON activities;
DROP TRIGGER work_member_identity ON project_members;
DROP TRIGGER work_state_identity ON states;
DROP TRIGGER work_project_identity ON projects;
DROP FUNCTION work_receipt_complete();
DROP FUNCTION work_receipt_guard();
DROP FUNCTION work_outbox_guard();
DROP FUNCTION work_activity_guard();
DROP FUNCTION work_member_guard();
DROP FUNCTION work_subject_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
        ("messaging", "0002_alter_outboxevent_created_at"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
