"""The hand-written MySQL DDL must match the parent table's collation, or MySQL refuses the foreign key (errno 150)."""
import importlib


class FakeCursor:
    def __init__(self):
        self.last = ''

    def execute(self, sql, params=None):
        self.last = sql

    def fetchone(self):
        return ('char',) if 'data_type' in self.last else ('utf8mb4_unicode_ci',)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConnection:
    vendor = 'mysql'

    def cursor(self):
        return FakeCursor()


def test_legacy_ddl_copies_the_parent_collation():
    m = importlib.import_module('clinic.migrations.0006_add_clinictestimonial')
    from spinalcure.migration_utils import mysql_ddl_or_schema_editor
    op = mysql_ddl_or_schema_editor('clinic', 'ClinicTestimonial', m.CREATE_SQL, m.DROP_SQL)
    ran = []

    class Editor:
        connection = FakeConnection()

        def execute(self, sql):
            ran.append(sql)

    op.code(None, Editor())
    assert len(ran) == 1 and 'DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci' in ran[0]
