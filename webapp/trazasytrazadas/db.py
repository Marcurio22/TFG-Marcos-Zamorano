"""
===============================================================================
Integración de Flask-SQLAlchemy y compatibilidad temporal con SQLite legacy.

Este módulo pasa a centralizar:
- la instancia db = SQLAlchemy(),
- la inicialización del esquema,
- una capa de compatibilidad temporal con sqlite3 para el código aún no
  migrado,
- y las migraciones aditivas mínimas para bases de datos existentes.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()


def get_db() -> sqlite3.Connection:
    """
    Devuelve una conexión sqlite3 legacy asociada al contexto actual.

    Se mantiene temporalmente para no romper el código que aún usa acceso
    manual mientras migramos gradualmente a Flask-SQLAlchemy.
    """
    if "legacy_db" not in g:
        database_path = current_app.config["DATABASE"]
        connection = sqlite3.connect(
            database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.legacy_db = connection

    return g.legacy_db


def close_db(_error=None) -> None:
    """Cierra la conexión sqlite3 legacy si existe en el contexto actual."""
    connection = g.pop("legacy_db", None)
    if connection is not None:
        connection.close()


def _table_columns(database: sqlite3.Connection, table_name: str) -> set[str]:
    """Devuelve el conjunto de columnas actuales de una tabla SQLite."""
    rows = database.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_legacy_schema(database: sqlite3.Connection) -> None:
    """
    Aplica migraciones aditivas mínimas para
        compatibilidad con BBDD existentes.

    De momento centraliza aquí la deuda actual:
    - columnas de estado de foto
    - nombre_coleccion en parcela
    """
    photo_columns = _table_columns(database, "foto")
    parcel_columns = _table_columns(database, "parcela")
    user_columns = _table_columns(database, "usuario")
    statements: list[str] = []

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
    if "nombre_coleccion" not in parcel_columns:
        statements.append(
            "ALTER TABLE parcela ADD COLUMN nombre_coleccion TEXT"
        )
    if "telefono" not in user_columns:
        statements.append(
            "ALTER TABLE usuario ADD COLUMN telefono TEXT"
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


def _ensure_system_user() -> None:
    """
    Garantiza que exista el usuario técnico por defecto.
    """
    db.session.execute(
        text(
            """
            INSERT OR IGNORE INTO usuario (
                usuario_id,
                nombre_usuario,
                contrasena,
                correo_electronico,
                rol
            )
            VALUES (
                1,
                'system',
                'disabled',
                'system@local.invalid',
                'system'
            )
            """
        )
    )
    db.session.commit()


def init_db() -> None:
    """Inicializa la base de datos."""
    legacy_db = get_db()

    with current_app.open_resource("schema.sql") as schema_file:
        legacy_db.executescript(schema_file.read().decode("utf-8"))
    legacy_db.commit()

    _migrate_legacy_schema(legacy_db)

    # Import local para registrar los modelos antes de create_all().
    from . import models  # noqa: F401

    db.create_all()
    _ensure_system_user()


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Comando CLI para inicializar manualmente la base de datos."""
    init_db()
    click.echo("Base de datos inicializada.")


def init_app(app) -> None:
    """Integra SQLite legacy y Flask-SQLAlchemy con la aplicación Flask."""
    db.init_app(app)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
