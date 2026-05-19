"""
===============================================================================
Integración de Flask-SQLAlchemy.

Este módulo centraliza la instancia db = SQLAlchemy(), la inicialización del
esquema a partir de modelos Python y las operaciones mínimas de bootstrap de
datos técnicos. No mantiene conexiones manuales ni carga esquemas SQL externos.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import click
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


db = SQLAlchemy()


def _ensure_parcela_paused_status() -> None:
    """Amplía el CHECK de parcela.estado para aceptar paused."""
    if db.engine.dialect.name != "sqlite":
        return

    table_sql = db.session.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'parcela'"
        )
    ).scalar_one_or_none()
    if not table_sql or "'paused'" in table_sql:
        return

    db.session.commit()
    with db.engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.exec_driver_sql("ALTER TABLE parcela RENAME TO parcela_old")
        connection.exec_driver_sql(
            "CREATE TABLE parcela ("
            "parcela_id INTEGER NOT NULL, "
            "usuario_id INTEGER NOT NULL, "
            "tamano_metros FLOAT NOT NULL, "
            "pto_origen_latitud FLOAT NOT NULL, "
            "pto_origen_longitud FLOAT NOT NULL, "
            "pto_fin_latitud FLOAT NOT NULL, "
            "pto_fin_longitud FLOAT NOT NULL, "
            "fuente_id TEXT NOT NULL, "
            "fuente_nombre TEXT NOT NULL, "
            "resolucion_solicitada FLOAT NOT NULL, "
            "resolucion_real FLOAT NOT NULL, "
            "ancho_tesela INTEGER NOT NULL, "
            "alto_tesela INTEGER NOT NULL, "
            "estado TEXT DEFAULT 'pending' NOT NULL, "
            "nombre_coleccion TEXT, "
            "creado_en TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "PRIMARY KEY (parcela_id), "
            "CONSTRAINT ck_parcela_estado CHECK "
            "(estado IN ('pending', 'processing', 'completed', "
            "'failed', 'paused')), "
            "FOREIGN KEY(usuario_id) REFERENCES usuario (usuario_id) "
            "ON DELETE CASCADE"
            ")"
        )
        connection.exec_driver_sql(
            "INSERT INTO parcela ("
            "parcela_id, usuario_id, tamano_metros, "
            "pto_origen_latitud, pto_origen_longitud, "
            "pto_fin_latitud, pto_fin_longitud, fuente_id, "
            "fuente_nombre, resolucion_solicitada, resolucion_real, "
            "ancho_tesela, alto_tesela, estado, nombre_coleccion, "
            "creado_en, actualizado_en"
            ") SELECT "
            "parcela_id, usuario_id, tamano_metros, "
            "pto_origen_latitud, pto_origen_longitud, "
            "pto_fin_latitud, pto_fin_longitud, fuente_id, "
            "fuente_nombre, resolucion_solicitada, resolucion_real, "
            "ancho_tesela, alto_tesela, estado, nombre_coleccion, "
            "creado_en, actualizado_en FROM parcela_old"
        )
        connection.exec_driver_sql("DROP TABLE parcela_old")
        connection.exec_driver_sql(
            "CREATE INDEX idx_parcela_usuario_fecha "
            "ON parcela (usuario_id, creado_en)"
        )
        connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_system_user() -> None:
    """Garantiza que exista el usuario técnico por defecto."""
    from .models import Usuario

    system_user = db.session.get(Usuario, 1)
    if system_user is None:
        system_user = Usuario(
            usuario_id=1,
            nombre_usuario="system",
            contrasena="disabled",
            correo_electronico="system@local.invalid",
            rol="system",
        )
        db.session.add(system_user)
        db.session.commit()
        return

    changed = False
    expected_values = {
        "nombre_usuario": "system",
        "contrasena": "disabled",
        "correo_electronico": "system@local.invalid",
        "rol": "system",
    }

    for attr_name, expected_value in expected_values.items():
        if getattr(system_user, attr_name) != expected_value:
            setattr(system_user, attr_name, expected_value)
            changed = True

    if changed:
        db.session.commit()


def init_db() -> None:
    """Inicializa la base de datos desde los modelos SQLAlchemy."""
    from . import models  # noqa: F401
    from .model_store import sync_models_from_files

    db.create_all()
    _ensure_parcela_paused_status()

    _ensure_system_user()
    sync_models_from_files()

    from .seed_data import load_demo_data_if_needed

    load_demo_data_if_needed()


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    """Comando CLI para inicializar manualmente la base de datos."""
    init_db()
    click.echo("Base de datos inicializada.")


def init_app(app) -> None:
    """Integra Flask-SQLAlchemy con la aplicación Flask."""
    db.init_app(app)
    app.cli.add_command(init_db_command)
