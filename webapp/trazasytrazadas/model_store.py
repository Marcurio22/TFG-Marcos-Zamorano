"""
===============================================================================
Utilidades de gestión de modelos.

Centraliza:
- listado de ficheros fold.N reales,
- sincronización con la tabla modelo,
- resolución del modelo activo,
- alta validada de nuevos modelos,
- renombrado seguro de modelos,
- eliminación segura de modelos,
- y metadatos opcionales de validación.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from flask import current_app, has_app_context
from werkzeug.utils import secure_filename

from .db import db
from .models import Modelo

_FOLD_FILENAME_RE = re.compile(r"^fold\.(\d+)$")
_METADATA_SUFFIX = ".metadata.json"


def _get_models_dir(models_dir: str | Path | None = None) -> Path:
    """Devuelve el directorio configurado de modelos."""
    if models_dir is not None:
        return Path(models_dir)

    if not has_app_context():
        raise RuntimeError(
            "No hay contexto Flask y no se ha proporcionado models_dir."
        )

    return Path(current_app.config["SEG_MODELS_DIR"])


def _metadata_path_for_fold_path(fold_path: Path) -> Path:
    """Devuelve la ruta del metadato sidecar asociado a un fold."""
    return fold_path.with_name(f".{fold_path.name}{_METADATA_SUFFIX}")


def _metadata_path_for_fold_name(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> Path:
    """Devuelve la ruta del sidecar de metadatos de un fold."""
    models_path = _get_models_dir(models_dir) / fold_name
    return _metadata_path_for_fold_path(models_path)


def is_valid_fold_name(name: str) -> bool:
    """Comprueba si un nombre sigue el patrón fold.N."""
    return _FOLD_FILENAME_RE.fullmatch((name or "").strip()) is not None


def parse_fold_index_from_name(name: str) -> int | None:
    """Extrae el índice numérico desde un nombre fold.N."""
    match = _FOLD_FILENAME_RE.fullmatch((name or "").strip())
    if match is None:
        return None
    return int(match.group(1))


def read_fold_metadata(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> dict:
    """Lee los metadatos opcionales de un fold."""
    normalized_name = (fold_name or "").strip()
    if not is_valid_fold_name(normalized_name):
        return {}

    metadata_path = _metadata_path_for_fold_name(normalized_name, models_dir)
    if not metadata_path.exists():
        return {}

    try:
        with metadata_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def write_fold_metadata(
    fold_name: str,
    metadata: dict,
    models_dir: str | Path | None = None,
) -> None:
    """Persiste metadatos opcionales de un fold en un sidecar JSON."""
    normalized_name = (fold_name or "").strip()
    if not is_valid_fold_name(normalized_name):
        raise ValueError("El nombre del modelo debe seguir el formato fold.N.")

    metadata_path = _metadata_path_for_fold_name(normalized_name, models_dir)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_fold_metadata(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Elimina el sidecar de metadatos de un fold si existe."""
    metadata_path = _metadata_path_for_fold_name(fold_name, models_dir)
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass


def list_fold_files(models_dir: str | Path | None = None) -> list[dict]:
    """Lista los ficheros fold.N reales presentes en el directorio."""
    resolved_models_dir = _get_models_dir(models_dir)
    if not resolved_models_dir.exists():
        return []

    folds = []
    for path in resolved_models_dir.iterdir():
        if not path.is_file():
            continue
        if not is_valid_fold_name(path.name):
            continue

        index = parse_fold_index_from_name(path.name)
        if index is None:
            continue

        folds.append(
            {
                "name": path.name,
                "index": index,
                "path": path,
                "metadata": read_fold_metadata(
                    path.name,
                    models_dir=resolved_models_dir,
                ),
            }
        )

    folds.sort(key=lambda item: item["index"])
    return folds


def _available_file_names(models_dir: str | Path | None = None) -> set[str]:
    """Devuelve los nombres de modelos presentes físicamente."""
    return {fold["name"] for fold in list_fold_files(models_dir=models_dir)}


def sync_models_from_files(models_dir: str | Path | None = None) -> None:
    """Sincroniza la tabla modelo con los ficheros fold.N existentes."""
    if not has_app_context():
        return

    folds = list_fold_files(models_dir=models_dir)
    existing_models = {
        model.nombre_modelo: model
        for model in db.session.execute(db.select(Modelo)).scalars().all()
    }

    for fold in folds:
        if fold["name"] in existing_models:
            continue

        db.session.add(
            Modelo(
                nombre_modelo=fold["name"],
                estado="no_activo",
                validacion="validado",
            )
        )

    db.session.commit()
    _ensure_active_model(models_dir=models_dir)


def _ensure_active_model(models_dir: str | Path | None = None) -> None:
    """Garantiza un único modelo activo validado si hay modelos disponibles."""
    if not has_app_context():
        return

    available_names = _available_file_names(models_dir=models_dir)
    models = db.session.execute(
        db.select(Modelo).order_by(Modelo.modelo_id.asc())
    ).scalars().all()

    valid_models = [
        model
        for model in models
        if model.nombre_modelo in available_names
        and model.validacion == "validado"
    ]

    if not valid_models:
        return

    active_models = [
        model for model in valid_models if model.estado == "activo"
    ]
    if len(active_models) == 1:
        return

    default_name = current_app.config.get(
        "SEG_DEFAULT_ACTIVE_FOLD",
        "fold.0",
    )
    selected = next(
        (
            model
            for model in valid_models
            if model.nombre_modelo == default_name
        ),
        valid_models[0],
    )

    for model in models:
        model.estado = (
            "activo"
            if model.modelo_id == selected.modelo_id
            else "no_activo"
        )

    db.session.commit()


def list_model_rows(models_dir: str | Path | None = None) -> list[dict]:
    """Lista modelos registrados junto con su estado físico."""
    sync_models_from_files(models_dir=models_dir)

    available_files = {
        fold["name"]: fold for fold in list_fold_files(models_dir=models_dir)
    }
    models = db.session.execute(
        db.select(Modelo).order_by(Modelo.nombre_modelo.asc())
    ).scalars().all()

    rows = []
    for model in models:
        fold_index = parse_fold_index_from_name(model.nombre_modelo)
        metadata = read_fold_metadata(
            model.nombre_modelo,
            models_dir=models_dir,
        )

        rows.append(
            {
                "modelo_id": model.modelo_id,
                "name": model.nombre_modelo,
                "index": fold_index,
                "estado": model.estado,
                "validacion": model.validacion,
                "is_active": model.estado == "activo",
                "file_exists": model.nombre_modelo in available_files,
                "metadata": metadata,
            }
        )

    rows.sort(
        key=lambda row: (
            row["index"] is None,
            row["index"] if row["index"] is not None else row["name"],
        )
    )
    return rows


def get_active_model() -> Modelo | None:
    """Devuelve el modelo activo persistido."""
    if not has_app_context():
        return None

    sync_models_from_files()
    return db.session.execute(
        db.select(Modelo).where(
            Modelo.estado == "activo",
            Modelo.validacion == "validado",
        )
    ).scalar_one_or_none()


def get_active_fold_name(
    models_dir: str | Path | None = None,
    default_name: str | None = None,
) -> str | None:
    """Devuelve el nombre del fold activo."""
    if has_app_context():
        active_model = get_active_model()
        if active_model is not None:
            return active_model.nombre_modelo

    folds = list_fold_files(models_dir=models_dir)
    if not folds:
        return default_name or "fold.0"

    available_names = {fold["name"] for fold in folds}
    fallback = default_name or "fold.0"

    if fallback in available_names:
        return fallback

    return folds[0]["name"]


def set_active_fold_name(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Marca un modelo validado como activo y desactiva el resto."""
    normalized_name = (fold_name or "").strip()

    if not is_valid_fold_name(normalized_name):
        raise ValueError("El modelo seleccionado no sigue el formato fold.N.")

    if normalized_name not in _available_file_names(models_dir=models_dir):
        raise FileNotFoundError(
            "El modelo seleccionado no existe en el directorio de modelos."
        )

    model = db.session.execute(
        db.select(Modelo).where(Modelo.nombre_modelo == normalized_name)
    ).scalar_one_or_none()

    if model is None:
        model = Modelo(
            nombre_modelo=normalized_name,
            estado="no_activo",
            validacion="validado",
        )
        db.session.add(model)
        db.session.flush()

    if model.validacion != "validado":
        raise ValueError(
            "No se puede activar un modelo pendiente de validación.")

    models = db.session.execute(db.select(Modelo)).scalars().all()
    for existing_model in models:
        existing_model.estado = (
            "activo"
            if existing_model.modelo_id == model.modelo_id
            else "no_activo"
        )

    db.session.commit()


def rename_fold_file(
    current_name: str,
    new_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Renombra un modelo en disco y en base de datos."""
    current_name = (current_name or "").strip()
    new_name = (new_name or "").strip()

    if not is_valid_fold_name(current_name):
        raise ValueError("El modelo actual no es válido.")

    if not is_valid_fold_name(new_name):
        raise ValueError("El nuevo nombre debe seguir el formato fold.N.")

    if current_name == new_name:
        raise ValueError("El nuevo nombre debe ser diferente del actual.")

    resolved_models_dir = _get_models_dir(models_dir)
    current_path = resolved_models_dir / current_name
    new_path = resolved_models_dir / new_name

    if not current_path.exists():
        raise FileNotFoundError("El modelo actual no existe.")

    if new_path.exists():
        raise FileExistsError("Ya existe otro modelo con ese nombre.")

    existing_model = db.session.execute(
        db.select(Modelo).where(Modelo.nombre_modelo == new_name)
    ).scalar_one_or_none()
    if existing_model is not None:
        raise FileExistsError("Ya existe otro modelo con ese nombre.")

    model = db.session.execute(
        db.select(Modelo).where(Modelo.nombre_modelo == current_name)
    ).scalar_one_or_none()

    current_metadata_path = _metadata_path_for_fold_path(current_path)
    new_metadata_path = _metadata_path_for_fold_path(new_path)

    current_path.rename(new_path)

    if current_metadata_path.exists():
        try:
            current_metadata_path.rename(new_metadata_path)
        except OSError:
            pass

    if model is None:
        model = Modelo(
            nombre_modelo=new_name,
            estado="no_activo",
            validacion="validado",
        )
        db.session.add(model)
    else:
        model.nombre_modelo = new_name

    db.session.commit()


def add_fold_file(
    fold_name: str,
    file_storage,
    *,
    validator=None,
    models_dir: str | Path | None = None,
) -> Path:
    """Guarda un nuevo fold tras validarlo en una ruta temporal."""
    normalized_name = (fold_name or "").strip()

    if not is_valid_fold_name(normalized_name):
        raise ValueError("El nombre del modelo debe seguir el formato fold.N.")

    if file_storage is None:
        raise ValueError("Selecciona un archivo de modelo.")

    resolved_models_dir = _get_models_dir(models_dir)
    resolved_models_dir.mkdir(parents=True, exist_ok=True)

    final_path = resolved_models_dir / normalized_name
    if final_path.exists():
        raise FileExistsError("Ya existe otro modelo con ese nombre.")

    existing_model = None
    if has_app_context():
        existing_model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == normalized_name)
        ).scalar_one_or_none()
        if existing_model is not None:
            raise FileExistsError("Ya existe otro modelo con ese nombre.")

    temp_path = (
        resolved_models_dir
        / f".{normalized_name}.{uuid.uuid4().hex}.upload"
    )

    try:
        file_storage.save(temp_path)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise ValueError("El archivo de modelo está vacío.")

        validation_result = None
        if validator is not None:
            validation_result = validator(temp_path)

        temp_path.replace(final_path)

        if isinstance(validation_result, dict):
            metadata = dict(validation_result)
            metadata.setdefault(
                "source_filename",
                secure_filename(file_storage.filename or ""),
            )
            metadata.setdefault("metadata_version", 1)
            write_fold_metadata(
                normalized_name,
                metadata,
                models_dir=resolved_models_dir,
            )

        if has_app_context():
            model = Modelo(
                nombre_modelo=normalized_name,
                estado="no_activo",
                validacion="validado",
            )
            db.session.add(model)
            db.session.commit()
            _ensure_active_model(models_dir=resolved_models_dir)

        return final_path
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def delete_fold_file(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Elimina un modelo no activo y su metadato asociado."""
    normalized_name = (fold_name or "").strip()

    if not is_valid_fold_name(normalized_name):
        raise ValueError("El modelo seleccionado no es válido.")

    resolved_models_dir = _get_models_dir(models_dir)
    fold_path = resolved_models_dir / normalized_name

    if not fold_path.exists():
        raise FileNotFoundError("El modelo seleccionado no existe.")

    model = None
    if has_app_context():
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == normalized_name)
        ).scalar_one_or_none()
        if model is not None and model.estado == "activo":
            raise ValueError(
                "No se puede eliminar el modelo activo. "
                "Activa otro fold antes de eliminar este."
            )

    active_name = get_active_fold_name(models_dir=resolved_models_dir)
    if active_name == normalized_name:
        raise ValueError(
            "No se puede eliminar el modelo activo. "
            "Activa otro fold antes de eliminar este."
        )

    fold_path.unlink()
    delete_fold_metadata(normalized_name, models_dir=resolved_models_dir)

    if has_app_context() and model is not None:
        db.session.delete(model)
        db.session.commit()
        _ensure_active_model(models_dir=resolved_models_dir)
