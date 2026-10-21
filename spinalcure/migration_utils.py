"""Helpers for migrations that carry hand-written MySQL DDL."""
from django.db import migrations


def mysql_ddl_or_schema_editor(app_label, model_name, create_sql, drop_sql):
    """
    Create/drop a table with hand-tuned DDL on MySQL (preserving what existing
    deployments already ran) and with Django's schema editor on any other
    backend. Place it AFTER a state-only CreateModel so the model exists in state.
    """
    import re
    statements = [create_sql] if isinstance(create_sql, str) else list(create_sql)
    referenced = sorted(set(re.findall(r'REFERENCES\s+`(\w+)`', ' '.join(statements))))

    def legacy_char32_keys(connection):
        """True when the tables this DDL points at keep UUIDs as char(32) (databases created before MariaDB's
        native uuid type). A fresh MariaDB 10.7+ database has native uuid keys, and the hand-written char(32)
        columns would not match them, so Django creates the table instead."""
        with connection.cursor() as cur:
            for table in referenced:
                cur.execute("SELECT data_type FROM information_schema.columns "
                            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'id'", [table])
                row = cur.fetchone()
                if row and row[0].lower() != 'char':
                    return False
        return True

    def forwards(apps, schema_editor):
        if schema_editor.connection.vendor == 'mysql' and legacy_char32_keys(schema_editor.connection):
            for statement in statements:
                schema_editor.execute(statement)
        else:
            schema_editor.create_model(apps.get_model(app_label, model_name))

    def backwards(apps, schema_editor):
        if schema_editor.connection.vendor == 'mysql':
            schema_editor.execute(drop_sql)
        else:
            schema_editor.delete_model(apps.get_model(app_label, model_name))

    return migrations.RunPython(forwards, backwards, atomic=False)
