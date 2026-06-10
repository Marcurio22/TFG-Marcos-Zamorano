"""Configuración de Gunicorn para trazasytrazadas en Docker.

Define los parámetros de ejecución del servidor WSGI Gunicorn, incluyendo el
número de trabajadores, hilos, tiempo de espera y opciones de logging.
Las configuraciones se pueden ajustar mediante variables de entorno para
facilitar la personalización en diferentes entornos de despliegue.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""

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
