from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.base import Base
from app.db.session import get_engine
from app.models import load_all_models


def _schema_name(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return cfg


def _create_orm_schema(schema: str) -> None:
    load_all_models()
    engine = get_engine()
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            Base.metadata.create_all(bind=connection)
            connection.commit()
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("SET search_path TO public")
            connection.commit()


def _create_alembic_schema(schema: str) -> None:
    engine = get_engine()
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            cfg = _alembic_config()
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
            connection.commit()
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("SET search_path TO public")
            connection.commit()


def _drop_schema(schema: str) -> None:
    engine = get_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _normalize_type(row) -> str:
    data_type = row["data_type"]
    udt_name = row["udt_name"]
    if udt_name == "jsonb":
        return "jsonb"
    if data_type == "character varying":
        return f"varchar({row['character_maximum_length']})"
    if data_type == "numeric":
        return f"numeric({row['numeric_precision']},{row['numeric_scale']})"
    if data_type == "timestamp with time zone":
        return "timestamptz"
    return udt_name


def _columns(schema: str) -> dict[tuple[str, str], tuple[str, bool]]:
    stmt = text(
        """
        SELECT table_name, column_name, data_type, udt_name,
               character_maximum_length, numeric_precision, numeric_scale, is_nullable
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name <> 'alembic_version'
        ORDER BY table_name, ordinal_position
        """
    )
    with get_engine().connect() as connection:
        rows = connection.execute(stmt, {"schema": schema}).mappings()
        return {
            (row["table_name"], row["column_name"]): (_normalize_type(row), row["is_nullable"] == "YES")
            for row in rows
        }


def _primary_and_unique_indexes(schema: str) -> set[tuple[str, str, tuple[str, ...]]]:
    stmt = text(
        """
        SELECT table_cls.relname AS table_name,
               index_info.indisprimary AS is_primary,
               index_info.indisunique AS is_unique,
               array_agg(attr.attname ORDER BY key_cols.ordinality) AS columns
        FROM pg_index index_info
        JOIN pg_class table_cls ON table_cls.oid = index_info.indrelid
        JOIN pg_namespace namespace ON namespace.oid = table_cls.relnamespace
        JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY AS key_cols(attnum, ordinality) ON true
        JOIN pg_attribute attr ON attr.attrelid = table_cls.oid AND attr.attnum = key_cols.attnum
        WHERE namespace.nspname = :schema
          AND table_cls.relname <> 'alembic_version'
          AND (index_info.indisprimary OR index_info.indisunique)
        GROUP BY table_cls.relname, index_info.indisprimary, index_info.indisunique, index_info.indexrelid
        ORDER BY table_cls.relname
        """
    )
    with get_engine().connect() as connection:
        rows = connection.execute(stmt, {"schema": schema}).mappings()
        return {
            (row["table_name"], "primary" if row["is_primary"] else "unique", tuple(row["columns"]))
            for row in rows
        }


def _foreign_keys(schema: str) -> set[tuple[str, str, str, str, str]]:
    stmt = text(
        """
        SELECT source_table.relname AS table_name,
               source_column.attname AS column_name,
               target_table.relname AS foreign_table_name,
               target_column.attname AS foreign_column_name,
               constraint_info.confdeltype AS on_delete
        FROM pg_constraint constraint_info
        JOIN pg_class source_table ON source_table.oid = constraint_info.conrelid
        JOIN pg_namespace namespace ON namespace.oid = source_table.relnamespace
        JOIN pg_class target_table ON target_table.oid = constraint_info.confrelid
        JOIN LATERAL unnest(constraint_info.conkey, constraint_info.confkey)
             AS key_cols(source_attnum, target_attnum) ON true
        JOIN pg_attribute source_column
             ON source_column.attrelid = source_table.oid AND source_column.attnum = key_cols.source_attnum
        JOIN pg_attribute target_column
             ON target_column.attrelid = target_table.oid AND target_column.attnum = key_cols.target_attnum
        WHERE namespace.nspname = :schema
          AND constraint_info.contype = 'f'
        """
    )
    delete_rules = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL"}
    with get_engine().connect() as connection:
        rows = connection.execute(stmt, {"schema": schema}).mappings()
        return {
            (
                row["table_name"],
                row["column_name"],
                row["foreign_table_name"],
                row["foreign_column_name"],
                delete_rules[row["on_delete"]],
            )
            for row in rows
        }


def test_alembic_baseline_matches_orm_metadata():
    orm_schema = _schema_name("trace_orm")
    alembic_schema = _schema_name("trace_alembic")
    try:
        _create_orm_schema(orm_schema)
        _create_alembic_schema(alembic_schema)

        assert _columns(alembic_schema) == _columns(orm_schema)
        assert _primary_and_unique_indexes(alembic_schema) == _primary_and_unique_indexes(orm_schema)
        assert _foreign_keys(alembic_schema) == _foreign_keys(orm_schema)
    finally:
        _drop_schema(alembic_schema)
        _drop_schema(orm_schema)
