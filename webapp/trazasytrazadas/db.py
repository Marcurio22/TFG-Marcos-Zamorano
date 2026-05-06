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
from flask import current_app
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select


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


def _reassign_legacy_parcels_to_configured_user() -> None:
    """Reasigna parcelas heredadas del usuario técnico a un usuario real."""
    from .models import Parcela, Usuario

    target_username = " ".join(
        (current_app.config.get("LEGACY_PARCEL_OWNER_USERNAME") or "").split()
    ).strip()

    if not target_username:
        return

    target_user = db.session.execute(
        select(Usuario).where(
            func.lower(Usuario.nombre_usuario) == target_username.lower()
        )
    ).scalar_one_or_none()

    if target_user is None or int(target_user.usuario_id) == 1:
        return

    non_system_parcel_count = db.session.execute(
        select(func.count(Parcela.parcela_id)).where(Parcela.usuario_id != 1)
    ).scalar_one()

    if int(non_system_parcel_count or 0) > 0:
        return

    system_parcels = db.session.execute(
        select(Parcela).where(Parcela.usuario_id == 1)
    ).scalars().all()

    if not system_parcels:
        return

    for parcel in system_parcels:
        parcel.usuario_id = int(target_user.usuario_id)

    db.session.commit()


def init_db() -> None:
    """Inicializa la base de datos desde los modelos SQLAlchemy."""
    from . import models  # noqa: F401  Registra modelos antes de create_all().

    db.create_all()
    _ensure_system_user()
    _reassign_legacy_parcels_to_configured_user()


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
