"""
===============================================================================
Worker CLI y automático para cálculo de trazas en segundo plano.

Esta implementación permite seguir usando el comando CLI manual, pero además
lanza el worker automáticamente en background cuando la aplicación empieza a
recibir peticiones, sin requerir acciones manuales del usuario.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import threading
import time

import click
from flask import current_app
from flask.cli import with_appcontext

from .collection_store import (
    claim_pending_photos,
    mark_photo_completed,
    mark_photo_failed,
    materialize_photo_tile,
    save_photo_traces_result,
)
from .segmentation_inference import compute_traces_from_segmentation


def _compute_photo_traces(image_path: str) -> dict:
    """Ejecuta la inferencia de segmentación con la configuración actual."""
    cfg = current_app.config
    return compute_traces_from_segmentation(
        image_path=image_path,
        models_dir=cfg["SEG_MODELS_DIR"],
        model_template=cfg["SEG_MODEL_TEMPLATE"],
        n_folds=cfg["SEG_N_FOLDS"],
        use_gpu=cfg["SEG_USE_GPU"],
    )


def _process_claimed_photo(photo: dict) -> None:
    """Procesa una foto ya reclamada y actualiza su estado final."""
    image_absolute_path = materialize_photo_tile(photo)
    traces = _compute_photo_traces(image_absolute_path)
    trace_relative_path = save_photo_traces_result(photo, traces)
    mark_photo_completed(photo["foto_id"], trace_relative_path)


def run_trace_worker(
    *,
    once: bool = False,
    batch_size: int = 1,
    poll_seconds: float = 2.0,
) -> int:
    """
    Ejecuta el bucle del worker.

    Returns:
        int: número de fotos procesadas correctamente.
    """
    processed_count = 0

    while True:
        claimed_photos = claim_pending_photos(limit=batch_size)

        if not claimed_photos:
            if once:
                break
            time.sleep(max(0.2, float(poll_seconds)))
            continue

        for photo in claimed_photos:
            try:
                _process_claimed_photo(photo)
                processed_count += 1
                current_app.logger.info(
                    "Foto %s procesada correctamente.",
                    photo["foto_id"],
                )
            except Exception as exc:  # pragma: no cover
                current_app.logger.exception(
                    "Error procesando foto %s",
                    photo["foto_id"],
                )
                mark_photo_failed(photo["foto_id"], str(exc))

        if once:
            continue

    return processed_count


def _background_worker_target(app) -> None:
    """Procesa la cola actual en un thread daemon lanzado bajo demanda."""
    with app.app_context():
        current_app.logger.info("Worker bajo demanda de trazas iniciado.")
        try:
            run_trace_worker(
                once=True,
                batch_size=app.config["TRACE_WORKER_BATCH_SIZE"],
                poll_seconds=app.config["TRACE_WORKER_POLL_SECONDS"],
            )
        except Exception:  # pragma: no cover
            current_app.logger.exception(
                "El worker bajo demanda de trazas se ha detenido por un error."
            )


def trigger_trace_worker(app) -> bool:
    """
    Lanza un worker daemon si no hay otro ya drenando la cola.

    Devuelve True si se ha arrancado un thread nuevo y False si no era
    necesario o el arranque automático está desactivado.
    """
    if not app.config.get("AUTO_START_TRACE_WORKER", True):
        return False

    if app.testing:
        return False

    state = app.extensions.setdefault("trace_worker", {})
    lock = state.setdefault("lock", threading.Lock())

    with lock:
        thread = state.get("thread")
        if thread is not None and thread.is_alive():
            return False

        thread = threading.Thread(
            target=_background_worker_target,
            args=(app,),
            name="trace-worker",
            daemon=True,
        )
        state["thread"] = thread
        thread.start()
        return True


def _ensure_background_worker_started(app) -> None:
    """
    Garantiza que exista un único worker automático en ejecución.

    Se invoca desde un hook de Flask antes de procesar peticiones. En tests se
    desactiva vía configuración para evitar efectos no deterministas.
    """
    if not app.config.get("AUTO_START_TRACE_WORKER", True):
        return

    if app.testing:
        return

    state = app.extensions.setdefault("trace_worker", {})
    lock = state.setdefault("lock", threading.Lock())

    with lock:
        thread = state.get("thread")
        if thread is not None and thread.is_alive():
            return

        thread = threading.Thread(
            target=_background_worker_target,
            args=(app,),
            name="trace-worker",
            daemon=True,
        )
        state["thread"] = thread
        thread.start()


@click.command("traces-worker")
@click.option(
    "--once",
    is_flag=True,
    help="Procesa la cola pendiente actual y termina.",
)
@click.option(
    "--batch-size",
    default=1,
    show_default=True,
    type=click.IntRange(1, 32),
    help="Número de fotos a reclamar por iteración.",
)
@click.option(
    "--poll-seconds",
    default=None,
    type=float,
    help="Segundos de espera entre consultas cuando no hay trabajo.",
)
@with_appcontext
def traces_worker_command(
    once: bool,
    batch_size: int,
    poll_seconds: float | None,
) -> None:
    """Comando CLI del worker de trazas."""
    effective_poll_seconds = (
        poll_seconds
        if poll_seconds is not None
        else current_app.config["TRACE_WORKER_POLL_SECONDS"]
    )

    processed = run_trace_worker(
        once=once,
        batch_size=batch_size,
        poll_seconds=effective_poll_seconds,
    )

    click.echo(f"Worker finalizado. Fotos procesadas: {processed}")


def init_app(app) -> None:
    """Registra el comando CLI del worker de trazas."""
    app.cli.add_command(traces_worker_command)
