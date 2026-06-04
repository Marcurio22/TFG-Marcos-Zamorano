#!/bin/sh
set -eu

if [ -z "${SECRET_KEY:-}" ]; then
    echo "ERROR: define SECRET_KEY en .env antes de arrancar." >&2
    exit 1
fi

mkdir -p \
    /app/instance/uploads \
    /app/instance/outputs \
    /app/instance/profile_images \
    /app/instance/collection \
    /app/instance/model

if [ ! -f /app/instance/config.py ]; then
    cat > /app/instance/config.py <<'PYCONFIG'
"""Configuración Docker generada para trazasytrazadas."""

from __future__ import annotations

import os
from pathlib import Path


BASE_INSTANCE_DIR = Path(
    os.environ.get("TRAZAS_INSTANCE_PATH", "/app/instance")
)


def _bool_from_env(name: str, default: bool = False) -> bool:
    """Lee una variable booleana desde el entorno."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _int_from_env(name: str, default: int) -> int:
    """Lee una variable entera desde el entorno."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_from_env(name: str, default: float) -> float:
    """Lee una variable decimal desde el entorno."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


SECRET_KEY = os.environ["SECRET_KEY"]

IMAGE_UPLOAD_MAX_CONTENT_LENGTH = _int_from_env(
    "IMAGE_UPLOAD_MAX_CONTENT_LENGTH",
    16 * 1024 * 1024,
)
MODEL_UPLOAD_MAX_CONTENT_LENGTH = _int_from_env(
    "MODEL_UPLOAD_MAX_CONTENT_LENGTH",
    2 * 1024 * 1024 * 1024,
)
MAX_CONTENT_LENGTH = _int_from_env(
    "MAX_CONTENT_LENGTH",
    max(IMAGE_UPLOAD_MAX_CONTENT_LENGTH, MODEL_UPLOAD_MAX_CONTENT_LENGTH),
)

DATABASE = os.environ.get(
    "DATABASE",
    str(BASE_INSTANCE_DIR / "trazasytrazadas.sqlite"),
)
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SQLALCHEMY_DATABASE_URI",
    f"sqlite:///{DATABASE}",
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

UPLOAD_FOLDER = str(BASE_INSTANCE_DIR / "uploads")
OUTPUT_FOLDER = str(BASE_INSTANCE_DIR / "outputs")
PROFILE_IMAGE_FOLDER = str(BASE_INSTANCE_DIR / "profile_images")
PROFILE_IMAGE_MAX_BYTES = _int_from_env(
    "PROFILE_IMAGE_MAX_BYTES",
    4 * 1024 * 1024,
)
COLLECTION_STORAGE_ROOT = str(BASE_INSTANCE_DIR / "collection")
SEG_MODELS_DIR = str(BASE_INSTANCE_DIR / "model")

SEG_DEFAULT_ACTIVE_FOLD = os.environ.get(
    "SEG_DEFAULT_ACTIVE_FOLD",
    "fold.0",
)
SEG_MODEL_TEMPLATE = os.environ.get("SEG_MODEL_TEMPLATE", "fold.{fold}")
SEG_N_FOLDS = _int_from_env("SEG_N_FOLDS", 10)
SEG_USE_GPU = _bool_from_env("SEG_USE_GPU", False)
MODEL_VALIDATION_USE_GPU = _bool_from_env(
    "MODEL_VALIDATION_USE_GPU",
    False,
)
MODEL_VALIDATION_IMAGE_SIZE = _int_from_env(
    "MODEL_VALIDATION_IMAGE_SIZE",
    128,
)

LOAD_DEMO_DATA = _bool_from_env("LOAD_DEMO_DATA", False)
DEMO_SQL_FILE = os.environ.get(
    "DEMO_SQL_FILE",
    "/app/webapp/trazasytrazadas/seed/demo_data.sql",
)
DEMO_STORAGE_DIR = os.environ.get(
    "DEMO_STORAGE_DIR",
    "/app/webapp/trazasytrazadas/seed/collection_storage",
)

AUTO_START_TRACE_WORKER = _bool_from_env("AUTO_START_TRACE_WORKER", True)
TRACE_WORKER_POLL_SECONDS = _float_from_env(
    "TRACE_WORKER_POLL_SECONDS",
    2.0,
)
TRACE_WORKER_BATCH_SIZE = _int_from_env("TRACE_WORKER_BATCH_SIZE", 1)
TRACE_WORKER_CONCURRENCY = _int_from_env("TRACE_WORKER_CONCURRENCY", 1)
TRACE_WORKER_STALE_SECONDS = _int_from_env(
    "TRACE_WORKER_STALE_SECONDS",
    600,
)
COLLECTION_PHOTO_RETRY_ENABLE_SECONDS = _int_from_env(
    "COLLECTION_PHOTO_RETRY_ENABLE_SECONDS",
    120,
)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = _bool_from_env("SESSION_COOKIE_SECURE", False)
PYCONFIG
fi

chown -R appuser:appuser /app/instance

exec gosu appuser "$@"
