"""Write guards protecting immutability of core_outbox_events and core_idempotency_records."""

from django.db import migrations

SQL = """
CREATE FUNCTION core_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF ROW(NEW.id, NEW.topic, NEW.producer, NEW.partition_key, NEW.stream_sequence,
           NEW.aggregate_type, NEW.aggregate_id, NEW.event_type, NEW.event_version,
           NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.topic, OLD.producer, OLD.partition_key, OLD.stream_sequence,
           OLD.aggregate_type, OLD.aggregate_id, OLD.event_type, OLD.event_version,
           OLD.created_at) THEN
      RAISE EXCEPTION 'Immutable event envelope'
        USING ERRCODE='23514', CONSTRAINT='chk_core_outbox_immutable';
    END IF;
    IF NEW.data IS DISTINCT FROM OLD.data THEN
      -- Permit only expired mail secret redaction (data.data.secret -> null) for identity events.
      IF OLD.producer <> 'identity-service'
         OR NEW.data - 'data' IS DISTINCT FROM OLD.data - 'data'
         OR (NEW.data->'data') - 'secret' IS DISTINCT FROM (OLD.data->'data') - 'secret'
         OR jsonb_typeof(NEW.data->'data'->'secret') IS DISTINCT FROM 'null' THEN
        RAISE EXCEPTION 'Immutable event payload'
          USING ERRCODE='23514', CONSTRAINT='chk_core_outbox_immutable';
      END IF;
    END IF;
  END IF;
  IF TG_OP = 'INSERT' AND (
      jsonb_typeof(NEW.data) IS DISTINCT FROM 'object'
      OR NEW.data->>'event_id' IS DISTINCT FROM NEW.id::text
      OR NEW.data->>'event_type' IS DISTINCT FROM NEW.event_type
      OR NEW.data->>'event_version' IS DISTINCT FROM NEW.event_version::text
      OR NEW.data->>'aggregate_id' IS DISTINCT FROM NEW.aggregate_id
      OR NEW.data->>'producer' IS DISTINCT FROM NEW.producer
      OR jsonb_typeof(NEW.data->'data') IS DISTINCT FROM 'object'
  ) THEN
    RAISE EXCEPTION 'Event metadata mismatch'
      USING ERRCODE='23514', CONSTRAINT='chk_core_outbox_envelope';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.producer = 'work-service' AND (
      NEW.stream_sequence IS NULL
      OR NEW.data->>'project_id' IS DISTINCT FROM NEW.partition_key
      OR NEW.data->>'project_sequence' IS DISTINCT FROM NEW.stream_sequence::text
      OR jsonb_typeof(NEW.data->'entity_version') IS DISTINCT FROM 'number'
  ) THEN
    RAISE EXCEPTION 'Work event metadata mismatch'
      USING ERRCODE='23514', CONSTRAINT='chk_core_outbox_envelope';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_outbox_immutable BEFORE INSERT OR UPDATE ON core_outbox_events
  FOR EACH ROW EXECUTE FUNCTION core_outbox_guard();

CREATE FUNCTION core_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'COMPLETED' AND ROW(
      NEW.id, NEW.domain, NEW.operation_id, NEW.actor_user_id, NEW.http_method,
      NEW.endpoint_path, NEW.idempotency_key, NEW.payload_hash, NEW.status,
      NEW.ai_proposal_id, NEW.ai_item_id, NEW.response_status, NEW.response_body, NEW.created_at
  ) IS DISTINCT FROM ROW(
      OLD.id, OLD.domain, OLD.operation_id, OLD.actor_user_id, OLD.http_method,
      OLD.endpoint_path, OLD.idempotency_key, OLD.payload_hash, OLD.status,
      OLD.ai_proposal_id, OLD.ai_item_id, OLD.response_status, OLD.response_body, OLD.created_at
  ) THEN
    RAISE EXCEPTION 'Immutable committed receipt'
      USING ERRCODE='23514', CONSTRAINT='chk_core_receipt_immutable';
  END IF;
  IF NEW.status = 'COMPLETED' AND (
      NEW.response_status IS NULL OR NEW.response_status < 200 OR NEW.response_status >= 300
      OR NEW.response_body IS NULL
      OR NEW.response_body->>'success' IS DISTINCT FROM 'true'
      OR (SELECT count(*) FROM jsonb_object_keys(NEW.response_body)) != 5
      OR NOT NEW.response_body ?& ARRAY['success','message','data','meta','error']
  ) THEN
    RAISE EXCEPTION 'Incomplete command receipt'
      USING ERRCODE='23514', CONSTRAINT='chk_core_receipt_complete';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_receipt_immutable BEFORE INSERT OR UPDATE ON core_idempotency_records
  FOR EACH ROW EXECUTE FUNCTION core_receipt_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS core_receipt_immutable ON core_idempotency_records;
DROP TRIGGER IF EXISTS core_outbox_immutable ON core_outbox_events;
DROP FUNCTION IF EXISTS core_receipt_guard();
DROP FUNCTION IF EXISTS core_outbox_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0001_initial"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
