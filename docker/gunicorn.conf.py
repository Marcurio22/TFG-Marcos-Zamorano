"""Configuración de Gunicorn para trazasytrazadas en Docker."""

from __future__ import annotations

import os


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


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# IMPORTANTE: mantener un solo proceso por defecto. La aplicación usa SQLite,
# hilos internos para worker/validación y ficheros auxiliares de eventos.
workers = _int_from_env("WEB_CONCURRENCY", 1)
threads = _int_from_env("GUNICORN_THREADS", 4)
worker_class = "gthread"

timeout = _int_from_env("GUNICORN_TIMEOUT", 300)
graceful_timeout = _int_from_env("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int_from_env("GUNICORN_KEEPALIVE", 5)

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True

preload_app = _bool_from_env("GUNICORN_PRELOAD", False)
worker_tmp_dir = os.environ.get(
    "GUNICORN_WORKER_TMP_DIR",
    "/app/instance/gunicorn-tmp",
)

max_requests = _int_from_env("GUNICORN_MAX_REQUESTS", 500)
max_requests_jitter = _int_from_env("GUNICORN_MAX_REQUESTS_JITTER", 50)
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")
