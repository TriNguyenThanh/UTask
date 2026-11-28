"""PostgreSQL triggers for display_name & audit immutability, plus canonical global roles."""

from django.db import migrations

from apps.accounts.roles import ROLE_SEEDS

DISPLAY_NAME_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION trigger_auto_generate_display_name()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.display_name IS NULL OR NEW.display_name = '' THEN
            NEW.display_name := trim(concat(NEW.last_name, ' ', NEW.first_name));
        END IF;
        IF NEW.display_name IS NULL OR NEW.display_name = '' THEN
            NEW.display_name := 'Thành viên UTask';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.display_name IS NULL OR NEW.display_name = ''
       OR NEW.first_name IS DISTINCT FROM OLD.first_name
       OR NEW.last_name IS DISTINCT FROM OLD.last_name THEN
        NEW.display_name := trim(concat(NEW.last_name, ' ', NEW.first_name));
        IF NEW.display_name = '' THEN
            NEW.display_name := 'Thành viên UTask';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_profile_display_name
BEFORE INSERT OR UPDATE ON user_profiles
FOR EACH ROW EXECUTE FUNCTION trigger_auto_generate_display_name();
"""

DROP_DISPLAY_NAME_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_user_profile_display_name ON user_profiles;
DROP FUNCTION IF EXISTS trigger_auto_generate_display_name();
"""

AUDIT_IMMUTABLE_TRIGGER_SQL = (
    "CREATE OR REPLACE FUNCTION trigger_prevent_audit_log_modification() "
    "RETURNS TRIGGER AS $$ "
    "BEGIN "
    "RAISE EXCEPTION 'Audit logs are immutable. UPDATE or DELETE "
    "operations are strictly prohibited.'; "
    "END; "
    "$$ LANGUAGE plpgsql;",
    "CREATE TRIGGER trg_audit_logs_immutable "
    "BEFORE UPDATE OR DELETE ON audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION trigger_prevent_audit_log_modification();",
)

DROP_AUDIT_IMMUTABLE_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;",
    "DROP FUNCTION IF EXISTS trigger_prevent_audit_log_modification();",
)


def seed_global_roles(apps, schema_editor):
    GlobalRole = apps.get_model("accounts", "GlobalRole")
    database = schema_editor.connection.alias
    for code, name, description in ROLE_SEEDS:
        GlobalRole.objects.using(database).get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=DISPLAY_NAME_TRIGGER_SQL,
            reverse_sql=DROP_DISPLAY_NAME_TRIGGER_SQL,
        ),
        migrations.RunSQL(
            sql=AUDIT_IMMUTABLE_TRIGGER_SQL,
            reverse_sql=DROP_AUDIT_IMMUTABLE_TRIGGER_SQL,
        ),
        migrations.RunPython(seed_global_roles, migrations.RunPython.noop),
    ]
