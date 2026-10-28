"""DB-API adapters. SQLite is restricted to synthetic tests, not live deployment."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


class Database:
    def __init__(self, connection, dialect):
        self.connection, self.dialect = connection, dialect
        self.depth = 0

    @classmethod
    def synthetic(cls):
        db = sqlite3.connect(':memory:', isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        result = cls(db, 'sqlite')
        db.executescript((ROOT/'migrations/001_recruitment.up.sql').read_text())
        for table in ['privacy_records', 'audit_events', 'recruitment_events']:
            for action in ['UPDATE', 'DELETE']:
                db.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON ewu2_{table} BEGIN SELECT RAISE(ABORT, 'Append-only evidence'); END")
        db.execute("INSERT INTO ewu2_schema_version VALUES(1,'synthetic-test')")
        return result

    @classmethod
    def postgres(cls, dsn):
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        db = cls(connection, 'postgres')
        if db.one('SELECT version FROM ewu2_schema_version WHERE version=1') is None:
            raise RuntimeError('Reviewed migration required')
        return db

    def execute(self, sql, values=()):
        return self.connection.execute(sql.replace('?', '%s') if self.dialect == 'postgres' else sql, values)

    def one(self, sql, values=()):
        row = self.execute(sql, values).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql, values=()):
        return [dict(row) for row in self.execute(sql, values).fetchall()]

    @contextmanager
    def transaction(self):
        if self.depth:
            self.depth += 1
            try:
                yield self
            finally:
                self.depth -= 1
            return
        self.execute('BEGIN IMMEDIATE' if self.dialect == 'sqlite' else 'BEGIN')
        self.depth = 1
        try:
            # One ordered audit chain and consistent read/check/write decisions across workers.
            if self.dialect == 'postgres':
                self.execute('SELECT singleton FROM ewu2_audit_head WHERE singleton=1 FOR UPDATE')
            yield self
            self.execute('COMMIT')
        except BaseException:
            self.execute('ROLLBACK')
            raise
        finally:
            self.depth = 0

    def close(self):
        self.connection.close()
