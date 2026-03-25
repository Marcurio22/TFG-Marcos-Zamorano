"""
===============================================================================
Utilidades de acceso e inicialización de SQLite para la aplicación.

Este módulo centraliza la apertura/cierre de conexiones, la creación del
esquema y la integración con la app factory de Flask.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db() -> sqlite3.Connection:
    """
    Devuelve la conexión SQLite asociada al contexto actual de Flask.

    La conexión se reutiliza dentro de la misma petición y activa claves
    foráneas para respetar la integridad referencial definida en el esquema.
    """
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


def init_db() -> None:
    """
    Crea el esquema SQLite de forma idempotente.

    El esquema vive en schema.sql para mantener la definición relacional en un
    único punto y facilitar su evolución.
    """
    database = get_db()
    with current_app.open_resource("schema.sql") as schema_file:
        database.executescript(schema_file.read().decode("utf-8"))
    database.commit()


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