"""
===============================================================================
Utilidades de acceso e inicialización de SQLite para la aplicación.

Este módulo centraliza la apertura/cierre de conexiones, la creación del
esquema y una migración ligera aditiva para compatibilidad con versiones
anteriores del esquema.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db() -> sqlite3.Connection:
    """Devuelve la conexión SQLite asociada al contexto actual de Flask."""
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        connection = sqlite3.connect(
            database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection

    return g.db


def close_db(_error=None) -> None:
    """Cierra la conexión SQLite si existe en el contexto actual."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def _table_columns(database: sqlite3.Connection, table_name: str) -> set[str]:
    """Devuelve el conjunto de columnas actuales de una tabla."""
    rows = database.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_collection_schema() -> None:
    """
    Aplica migraciones aditivas mínimas para fotos procesables en background.

    Se usa porque CREATE TABLE IF NOT EXISTS no modifica tablas ya existentes.
    """
    database = get_db()
    photo_columns = _table_columns(database, "foto")
    statements = []

    if "estado" not in photo_columns:
        statements.append(
            "ALTER TABLE foto ADD COLUMN estado "
            "TEXT NOT NULL DEFAULT 'pending'"
        )
    if "error_message" not in photo_columns:
        statements.append(
            "ALTER TABLE foto ADD COLUMN error_message TEXT"
        )
    if "started_at" not in photo_columns:
        statements.append(
            "ALTER TABLE foto ADD COLUMN started_at TEXT"
        )
    if "finished_at" not in photo_columns:
        statements.append(
            "ALTER TABLE foto ADD COLUMN finished_at TEXT"
        )
    if "attempt_count" not in photo_columns:
        statements.append(
            "ALTER TABLE foto ADD COLUMN attempt_count "
            "INTEGER NOT NULL DEFAULT 0"
        )

    for statement in statements:
        database.execute(statement)

    if statements:
        database.commit()

    # Normaliza filas antiguas ya marcadas con trazas.
    database.execute(
        """
        UPDATE foto
        SET estado = 'completed'
        WHERE trazas = 1 AND estado = 'pending'
        """
    )
    database.commit()


def init_db() -> None:
    """Crea el esquema SQLite y aplica migraciones aditivas."""
    database = get_db()
    with current_app.open_resource("schema.sql") as schema_file:
        database.executescript(schema_file.read().decode("utf-8"))
    database.commit()
    _migrate_collection_schema()


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Comando CLI para inicializar manualmente la base de datos."""
    init_db()
    click.echo("Base de datos inicializada.")


def init_app(app) -> None:
    """Integra SQLite con la aplicación Flask."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
