"""
Carga inicial de datos demo mediante sentencias INSERT INTO.

Este módulo solo ejecutaun fichero SQL de datos iniciales
cuando la base de datos está vacía.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

from __future__ import annotations

import shutil
from pathlib import Path

from flask import current_app
from sqlalchemy import text

from .db import db
from .models import Foto, Parcela, Usuario


def _is_database_empty() -> bool:
    """Comprueba si la BBDD no contiene datos reales de la aplicación."""
    user_count = db.session.execute(
        db.select(db.func.count(Usuario.usuario_id)).where(
            Usuario.rol != "system"
        )
    ).scalar_one()

    parcel_count = db.session.execute(
        db.select(db.func.count(Parcela.parcela_id))
    ).scalar_one()

    photo_count = db.session.execute(
        db.select(db.func.count(Foto.foto_id))
    ).scalar_one()

    return user_count == 0 and parcel_count == 0 and photo_count == 0


def _read_sql_statements(sql_file: Path) -> list[str]:
    """
    Lee un fichero SQL generado por la aplicación.

    El exportador genera una sentencia por bloque terminado en ';'. No se usa
    sqlite3 directamente; cada sentencia se ejecuta mediante SQLAlchemy.
    """
    content = sql_file.read_text(encoding="utf-8")
    statements: list[str] = []
    buffer: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("--"):
            continue

        buffer.append(raw_line)

        if line.endswith(";"):
            statement = "\n".join(buffer).strip()
            statement = statement[:-1].strip()
            if statement:
                statements.append(statement)
            buffer = []

    if buffer:
        statement = "\n".join(buffer).strip()
        if statement:
            statements.append(statement)

    return statements


def _execute_demo_sql(sql_file: Path) -> None:
    """Ejecuta las sentencias INSERT INTO del fichero demo."""
    statements = _read_sql_statements(sql_file)

    for statement in statements:
        db.session.execute(text(statement))


def _copy_demo_storage(seed_storage_dir: Path) -> None:
    """Copia las carpetas físicas demo al storage de colecciones."""
    if not seed_storage_dir.exists():
        return

    destination = Path(current_app.config["COLLECTION_STORAGE_ROOT"])
    destination.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        seed_storage_dir,
        destination,
        dirs_exist_ok=True,
    )


def load_demo_data_if_needed() -> None:
    """
    Carga datos demo si está activado, existe el SQL y la BBDD está vacía.
    """
    if not current_app.config.get("LOAD_DEMO_DATA", False):
        return

    if not _is_database_empty():
        return

    sql_file = Path(current_app.config["DEMO_SQL_FILE"])
    seed_storage_dir = Path(current_app.config["DEMO_STORAGE_DIR"])

    if not sql_file.exists():
        current_app.logger.warning(
            "LOAD_DEMO_DATA está activo, pero no existe %s.",
            sql_file,
        )
        return

    try:
        _execute_demo_sql(sql_file)
        db.session.commit()

        _copy_demo_storage(seed_storage_dir)

        current_app.logger.info("Datos demo cargados correctamente.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("No se pudieron cargar los datos demo.")
        raise
