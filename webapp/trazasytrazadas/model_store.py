"""
===============================================================================
Utilidades de gestión de folds/modelos.

Centraliza:
- listado de ficheros fold.N reales,
- resolución del fold activo persistido,
- renombrado seguro de folds,
- y actualización del fold activo en SQLite.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import re
from pathlib import Path

from flask import current_app, has_app_context

from .db import db
from .models import AppSetting

_FOLD_FILENAME_RE = re.compile(r"^fold\.(\d+)$")
_ACTIVE_FOLD_KEY = "active_fold_name"


def _get_models_dir(models_dir: str | Path | None = None) -> Path:
    """Devuelve el directorio configurado de modelos."""
    if models_dir is not None:
        return Path(models_dir)

    if not has_app_context():
        raise RuntimeError(
            "No hay contexto Flask y no se ha proporcionado models_dir."
        )

    return Path(current_app.config["SEG_MODELS_DIR"])


def is_valid_fold_name(name: str) -> bool:
    """Comprueba si un nombre sigue el patrón fold.N."""
    return _FOLD_FILENAME_RE.fullmatch((name or "").strip()) is not None


def parse_fold_index_from_name(name: str) -> int | None:
    """Extrae el índice numérico desde un nombre fold.N."""
    match = _FOLD_FILENAME_RE.fullmatch((name or "").strip())
    if match is None:
        return None
    return int(match.group(1))


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

    current_path.rename(new_path)

    if has_app_context() and active_before == current_name:
        setting = db.session.get(AppSetting, _ACTIVE_FOLD_KEY)
        if setting is None:
            setting = AppSetting(key=_ACTIVE_FOLD_KEY, value=new_name)
            db.session.add(setting)
        else:
            setting.value = new_name

        db.session.commit()
