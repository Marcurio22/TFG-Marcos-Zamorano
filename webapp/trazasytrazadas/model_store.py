"""
===============================================================================
Utilidades de gestión de folds/modelos.

Centraliza:
- listado de ficheros fold.N reales,
- resolución del fold activo persistido,
- renombrado seguro de folds,
- alta validada de nuevos folds,
- eliminación segura de folds,
- y actualización del fold activo en SQLite.

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
from .models import AppSetting

_FOLD_FILENAME_RE = re.compile(r"^fold\.(\d+)$")
_ACTIVE_FOLD_KEY = "active_fold_name"
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
        raise ValueError("El nombre del fold debe seguir el formato fold.N.")

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
    """Lista los folds reales presentes en el directorio de modelos."""
    resolved_models_dir = _get_models_dir(models_dir)
    if not resolved_models_dir.exists():
        return []

    folds = []
    for path in resolved_models_dir.iterdir():
        if not path.is_file():
            continue
        if not is_valid_fold_name(path.name):
            continue

        fold_index = parse_fold_index_from_name(path.name)
        if fold_index is None:
            continue

        folds.append(
            {
                "name": path.name,
                "index": fold_index,
                "path": path,
                "metadata": read_fold_metadata(
                    path.name,
                    models_dir=resolved_models_dir,
                ),
            }
        )

    folds.sort(key=lambda item: item["index"])
    return folds


def get_active_fold_name(
    models_dir: str | Path | None = None,
    default_name: str | None = None,
) -> str | None:
    """Devuelve el fold activo persistido o un fallback coherente."""
    folds = list_fold_files(models_dir=models_dir)
    if not folds:
        return None

    available_names = {fold["name"] for fold in folds}

    if has_app_context():
        setting = db.session.get(AppSetting, _ACTIVE_FOLD_KEY)
        if setting is not None and setting.value in available_names:
            return setting.value

        configured_default = current_app.config.get(
            "SEG_DEFAULT_ACTIVE_FOLD",
            "fold.0",
        )
    else:
        configured_default = default_name or "fold.0"

    if configured_default in available_names:
        return configured_default

    return folds[0]["name"]


def set_active_fold_name(
    fold_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Persiste el fold activo en SQLite."""
    normalized_name = (fold_name or "").strip()

    if not is_valid_fold_name(normalized_name):
        raise ValueError("El fold seleccionado no sigue el formato fold.N.")

    available_names = {
        fold["name"] for fold in list_fold_files(models_dir=models_dir)
    }
    if normalized_name not in available_names:
        raise FileNotFoundError(
            "El fold seleccionado no existe en el directorio de modelos."
        )

    setting = db.session.get(AppSetting, _ACTIVE_FOLD_KEY)
    if setting is None:
        setting = AppSetting(key=_ACTIVE_FOLD_KEY, value=normalized_name)
        db.session.add(setting)
    else:
        setting.value = normalized_name

    db.session.commit()


def rename_fold_file(
    current_name: str,
    new_name: str,
    models_dir: str | Path | None = None,
) -> None:
    """Renombra un fold y actualiza el activo si era el seleccionado."""
    current_name = (current_name or "").strip()
    new_name = (new_name or "").strip()

    if not is_valid_fold_name(current_name):
        raise ValueError("El fold actual no es válido.")

    if not is_valid_fold_name(new_name):
        raise ValueError("El nuevo nombre debe seguir el formato fold.N.")

    if current_name == new_name:
        raise ValueError("El nuevo nombre debe ser diferente del actual.")

    resolved_models_dir = _get_models_dir(models_dir)
    current_path = resolved_models_dir / current_name
    new_path = resolved_models_dir / new_name

    if not current_path.exists():
        raise FileNotFoundError("El fold actual no existe.")

    if new_path.exists():
        raise FileExistsError("Ya existe otro fold con ese nombre.")

    active_before = get_active_fold_name(models_dir=resolved_models_dir)
    current_metadata_path = _metadata_path_for_fold_path(current_path)
    new_metadata_path = _metadata_path_for_fold_path(new_path)

    current_path.rename(new_path)

    if current_metadata_path.exists():
        try:
            current_metadata_path.rename(new_metadata_path)
        except OSError:
            pass

    if has_app_context() and active_before == current_name:
        setting = db.session.get(AppSetting, _ACTIVE_FOLD_KEY)
        if setting is None:
            setting = AppSetting(key=_ACTIVE_FOLD_KEY, value=new_name)
            db.session.add(setting)
        else:
            setting.value = new_name

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
        raise ValueError("El nombre del fold debe seguir el formato fold.N.")

    if file_storage is None:
        raise ValueError("Selecciona un archivo de modelo.")

    resolved_models_dir = _get_models_dir(models_dir)
    resolved_models_dir.mkdir(parents=True, exist_ok=True)

    final_path = resolved_models_dir / normalized_name
    if final_path.exists():
        raise FileExistsError("Ya existe otro fold con ese nombre.")

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
    """Elimina un fold no activo y su metadato asociado."""
    normalized_name = (fold_name or "").strip()

    if not is_valid_fold_name(normalized_name):
        raise ValueError("El fold seleccionado no es válido.")

    resolved_models_dir = _get_models_dir(models_dir)
    fold_path = resolved_models_dir / normalized_name

    if not fold_path.exists():
        raise FileNotFoundError("El fold seleccionado no existe.")

    active_name = get_active_fold_name(models_dir=resolved_models_dir)
    if active_name == normalized_name:
        raise ValueError(
            "No se puede eliminar el modelo activo. "
            "Activa otro fold antes de eliminar este."
        )

    fold_path.unlink()
    delete_fold_metadata(normalized_name, models_dir=resolved_models_dir)
