"""Helpers for migrations that carry hand-written MySQL DDL."""
from django.db import migrations


def mysql_ddl_or_schema_editor(app_label, model_name, create_sql, drop_sql):
    """
    Create/drop a table with hand-tuned DDL on MySQL (preserving what existing
    deployments already ran) and with Django's schema editor on any other
    backend. Place it AFTER a state-only CreateModel so the model exists in state.
    """
    statements = [create_sql] if isinstance(create_sql, str) else list(create_sql)

    def forwards(apps, schema_editor):
        if schema_editor.connection.vendor == 'mysql':
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
