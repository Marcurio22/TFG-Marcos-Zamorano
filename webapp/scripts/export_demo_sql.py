"""
Exporta la BBDD actual a un fichero SQL con INSERT INTO.

Genera:
- trazasytrazadas/seed/demo_data.sql
- trazasytrazadas/seed/collection_storage/

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

from __future__ import annotations
from trazasytrazadas.db import db
from trazasytrazadas import create_app

import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Durante la exportación no queremos que create_app cargue datos demo.
os.environ["LOAD_DEMO_DATA"] = "false"


def _models():
    """Importa modelos cuando la app ya está disponible."""
    from trazasytrazadas.models import Foto, Modelo, Parcela, Usuario

    return Foto, Modelo, Parcela, Usuario


def _sql_literal(value: Any) -> str:
    """Convierte un valor Python en literal SQL seguro para SQLite."""
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, datetime):
        value = value.isoformat(timespec="seconds")
    elif isinstance(value, date):
        value = value.isoformat()

    text_value = str(value)
    text_value = text_value.replace("\r", " ").replace("\n", " ")
    text_value = text_value.replace("'", "''")
    return f"'{text_value}'"


def _sql_subquery_usuario(username: str) -> str:
    """Devuelve subconsulta para resolver usuario_id por nombre_usuario."""
    return (
        "(SELECT usuario_id FROM usuario "
        f"WHERE nombre_usuario = {_sql_literal(username)})"
    )


def _sql_subquery_modelo(model_name: str | None) -> str:
    """Devuelve subconsulta para resolver modelo_id por nombre_modelo."""
    if not model_name:
        return "NULL"

    return (
        "(SELECT modelo_id FROM modelo "
        f"WHERE nombre_modelo = {_sql_literal(model_name)})"
    )


def _insert_statement(table: str, values: dict[str, str]) -> str:
    """Construye un INSERT OR IGNORE."""
    columns = ", ".join(values.keys())
    sql_values = ", ".join(values.values())
    return f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({sql_values});"


def _export_users() -> list[str]:
    """Exporta usuarios reales. El usuario system se crea por la app."""
    _foto, _modelo, _parcela, Usuario = _models()
    statements: list[str] = []

    users = db.session.execute(
        db.select(Usuario)
        .where(Usuario.rol != "system")
        .order_by(Usuario.usuario_id.asc())
    ).scalars().all()

    for user in users:
        statements.append(
            _insert_statement(
                "usuario",
                {
                    "nombre_usuario": _sql_literal(user.nombre_usuario),
                    "contrasena": _sql_literal(user.contrasena),
                    "correo_electronico": _sql_literal(
                        user.correo_electronico
                    ),
                    "telefono": _sql_literal(user.telefono),
                    "rol": _sql_literal(user.rol),
                    "fecha_alta": _sql_literal(user.fecha_alta),
                    "ruta_imagen_perfil": _sql_literal(
                        user.ruta_imagen_perfil
                    ),
                },
            )
        )

    return statements


def _export_models() -> list[str]:
    """Exporta modelos registrados en BBDD."""
    _foto, Modelo, _parcela, _usuario = _models()
    statements: list[str] = []

    models = db.session.execute(
        db.select(Modelo).order_by(Modelo.modelo_id.asc())
    ).scalars().all()

    for model in models:
        statements.append(
            _insert_statement(
                "modelo",
                {
                    "nombre_modelo": _sql_literal(model.nombre_modelo),
                    "estado": _sql_literal(model.estado),
                    "validacion": _sql_literal(model.validacion),
                    "creado_en": _sql_literal(model.creado_en),
                    "actualizado_en": _sql_literal(model.actualizado_en),
                },
            )
        )

    return statements


def _export_parcels() -> list[str]:
    """Exporta parcelas usando el usuario por nombre, no por ID fijo."""
    _foto, _modelo, Parcela, Usuario = _models()
    statements: list[str] = []

    parcels = db.session.execute(
        db.select(Parcela)
        .join(Usuario, Usuario.usuario_id == Parcela.usuario_id)
        .order_by(Parcela.parcela_id.asc())
    ).scalars().all()

    for parcel in parcels:
        statements.append(
            _insert_statement(
                "parcela",
                {
                    "parcela_id": _sql_literal(parcel.parcela_id),
                    "usuario_id": _sql_subquery_usuario(
                        parcel.usuario.nombre_usuario
                    ),
                    "tamano_metros": _sql_literal(parcel.tamano_metros),
                    "pto_origen_latitud": _sql_literal(
                        parcel.pto_origen_latitud
                    ),
                    "pto_origen_longitud": _sql_literal(
                        parcel.pto_origen_longitud
                    ),
                    "pto_fin_latitud": _sql_literal(parcel.pto_fin_latitud),
                    "pto_fin_longitud": _sql_literal(
                        parcel.pto_fin_longitud
                    ),
                    "fuente_id": _sql_literal(parcel.fuente_id),
                    "fuente_nombre": _sql_literal(parcel.fuente_nombre),
                    "resolucion_solicitada": _sql_literal(
                        parcel.resolucion_solicitada
                    ),
                    "resolucion_real": _sql_literal(parcel.resolucion_real),
                    "ancho_tesela": _sql_literal(parcel.ancho_tesela),
                    "alto_tesela": _sql_literal(parcel.alto_tesela),
                    "estado": _sql_literal(parcel.estado),
                    "nombre_coleccion": _sql_literal(
                        parcel.nombre_coleccion
                    ),
                    "creado_en": _sql_literal(parcel.creado_en),
                    "actualizado_en": _sql_literal(parcel.actualizado_en),
                },
            )
        )

    return statements


def _export_photos() -> list[str]:
    """Exporta fotos usando el modelo por nombre, no por ID fijo."""
    Foto, _modelo, _parcela, _usuario = _models()
    statements: list[str] = []

    photos = db.session.execute(
        db.select(Foto).order_by(Foto.foto_id.asc())
    ).scalars().all()

    for photo in photos:
        model_name = photo.modelo.nombre_modelo if photo.modelo else None

        statements.append(
            _insert_statement(
                "foto",
                {
                    "foto_id": _sql_literal(photo.foto_id),
                    "parcela_id": _sql_literal(photo.parcela_id),
                    "modelo_id": _sql_subquery_modelo(model_name),
                    "fecha_foto": _sql_literal(photo.fecha_foto),
                    "resolucion_valor": _sql_literal(
                        photo.resolucion_valor
                    ),
                    "resolucion_unidad": _sql_literal(
                        photo.resolucion_unidad
                    ),
                    "longitud": _sql_literal(photo.longitud),
                    "latitud": _sql_literal(photo.latitud),
                    "ruta_foto": _sql_literal(photo.ruta_foto),
                    "ruta_trazas": _sql_literal(photo.ruta_trazas),
                    "trazas": _sql_literal(photo.trazas),
                    "estado": _sql_literal(photo.estado),
                    "mensaje_error": _sql_literal(photo.mensaje_error),
                    "iniciado_en": _sql_literal(photo.iniciado_en),
                    "finalizado_en": _sql_literal(photo.finalizado_en),
                    "numero_intentos": _sql_literal(photo.numero_intentos),
                    "tesela_id": _sql_literal(photo.tesela_id),
                    "indice_fila": _sql_literal(photo.indice_fila),
                    "indice_columna": _sql_literal(photo.indice_columna),
                    "nombre_archivo": _sql_literal(photo.nombre_archivo),
                    "ancho": _sql_literal(photo.ancho),
                    "alto": _sql_literal(photo.alto),
                    "limites_3857_json": _sql_literal(
                        photo.limites_3857_json
                    ),
                    "limites_json": _sql_literal(photo.limites_json),
                    "creado_en": _sql_literal(photo.creado_en),
                },
            )
        )

    return statements


def _copy_collection_storage(app, seed_dir: Path) -> None:
    """Copia el almacenamiento físico de colecciones al paquete demo."""
    source = Path(app.config["COLLECTION_STORAGE_ROOT"])
    destination = seed_dir / "collection_storage"

    if destination.exists():
        shutil.rmtree(destination)

    if source.exists():
        shutil.copytree(source, destination)
    else:
        destination.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Exporta la BBDD actual a demo_data.sql."""
    app = create_app()

    with app.app_context():
        root = Path(__file__).resolve().parents[1]
        seed_dir = root / "trazasytrazadas" / "seed"
        seed_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = [
            "-- Datos demo generados automáticamente.",
            "-- El esquema se crea mediante SQLAlchemy.",
            "-- Este fichero solo inserta datos iniciales.",
            "",
        ]

        lines.extend(_export_users())
        lines.append("")
        lines.extend(_export_models())
        lines.append("")
        lines.extend(_export_parcels())
        lines.append("")
        lines.extend(_export_photos())
        lines.append("")

        output_file = seed_dir / "demo_data.sql"
        output_file.write_text("\n".join(lines), encoding="utf-8")

        _copy_collection_storage(app, seed_dir)

        print(f"SQL demo exportado en: {output_file}")
        print(f"Storage demo exportado en: {seed_dir / 'collection_storage'}")


if __name__ == "__main__":
    main()
