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


db = SQLAlchemy()


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
