"""
===============================================================================
Pruebas de ejecución y arranque del worker de trazas.

Este módulo cubre ramas de arranque automático, ejecución bajo demanda y bucle
sin trabajo pendiente sin crear threads reales de larga duración.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from trazasytrazadas import trace_worker as worker_module


class _StopWorker(RuntimeError):
    """Excepción local para detener bucles deliberadamente en tests."""


def test_run_trace_worker_waits_when_empty_queue_and_continues(monkeypatch):
    """Verifica el worker de trazas en el caso previsto."""
    calls = {"claim": 0, "sleep": []}

    def fake_claim_pending_photos(limit):
        """Simula la cola vacía y luego detiene el worker."""
        calls["claim"] += 1
        if calls["claim"] == 1:
            return []
        raise _StopWorker("stop")

    monkeypatch.setattr(
        worker_module, "claim_pending_photos", fake_claim_pending_photos
    )
    monkeypatch.setattr(
        worker_module.time,
        "sleep",
        lambda seconds: calls["sleep"].append(seconds),
    )

    with pytest.raises(_StopWorker):
        worker_module.run_trace_worker(
            once=False, batch_size=3, poll_seconds=0.01
        )

    assert calls == {"claim": 2, "sleep": [0.2]}


def test_background_worker_target_runs_inside_app_context(app, monkeypatch):
    """Verifica que el worker de trazas ejecuta el caso previsto."""
    observed = {}

    def fake_run_trace_worker(**kwargs):
        """Registra la ejecución simulada del worker."""
        observed.update(kwargs)
        return 0

    monkeypatch.setattr(
        worker_module, "run_trace_worker", fake_run_trace_worker
    )
    app.config["TRACE_WORKER_BATCH_SIZE"] = 5
    app.config["TRACE_WORKER_POLL_SECONDS"] = 0.75

    worker_module._background_worker_target(app)

    assert observed == {"once": True, "batch_size": 5, "poll_seconds": 0.75}


def test_trigger_trace_worker_starts_thread_when_enabled(app, monkeypatch):
    """Verifica que el worker de trazas arranca el caso previsto."""
    app.config["AUTO_START_TRACE_WORKER"] = True
    app.config["TESTING"] = False
    started = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            """Inicializa el doble de prueba."""
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon
            started.append((target, args, name, daemon))

        def is_alive(self):
            """Indica si el hilo simulado está vivo."""
            return False

        def start(self):
            """Registra el inicio del hilo simulado."""
            started.append("started")

    monkeypatch.setattr(worker_module.threading, "Thread", FakeThread)

    assert worker_module.trigger_trace_worker(app) is True
    assert started[0][2:] == ("trace-worker", True)
    assert started[1] == "started"
    assert app.extensions["trace_worker"]["thread"].name == "trace-worker"


def test_ensure_background_worker_started_respects_flags(app, monkeypatch):
    """Verifica que el worker de trazas arranca el caso previsto."""
    created = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            """Inicializa el doble de prueba."""
            self.name = name
            self._alive = False
            created.append((target, args, name, daemon))

        def is_alive(self):
            """Indica si el hilo simulado está vivo."""
            return self._alive

        def start(self):
            """Registra el inicio del hilo simulado."""
            created.append("started")

    class AliveThread:
        def is_alive(self):
            """Indica si el hilo simulado está vivo."""
            return True

    monkeypatch.setattr(worker_module.threading, "Thread", FakeThread)

    app.config["AUTO_START_TRACE_WORKER"] = False
    worker_module._ensure_background_worker_started(app)
    assert created == []

    app.config["AUTO_START_TRACE_WORKER"] = True
    app.config["TESTING"] = True
    worker_module._ensure_background_worker_started(app)
    assert created == []

    app.config["TESTING"] = False
    app.extensions["trace_worker"] = {
        "lock": threading.Lock(),
        "thread": AliveThread(),
    }
    worker_module._ensure_background_worker_started(app)
    assert created == []

    app.extensions["trace_worker"] = {"lock": threading.Lock()}
    worker_module._ensure_background_worker_started(app)
    assert created[0][2:] == ("trace-worker", True)
    assert created[1] == "started"


def test_traces_worker_command_uses_default_poll_seconds(app, monkeypatch):
    """Verifica que el worker de trazas usa el caso previsto."""
    observed = {}

    def fake_run_trace_worker(**kwargs):
        """Registra la ejecución simulada del worker."""
        observed.update(kwargs)
        return 4

    monkeypatch.setattr(
        worker_module, "run_trace_worker", fake_run_trace_worker
    )
    app.config["TRACE_WORKER_POLL_SECONDS"] = 1.25

    result = app.test_cli_runner().invoke(
        args=["traces-worker", "--once", "--batch-size", "2"]
    )

    assert result.exit_code == 0
    assert observed == {"once": True, "batch_size": 2, "poll_seconds": 1.25}
    assert "Fotos procesadas: 4" in result.output


def test_run_trace_worker_pool_uses_configured_concurrency(app, monkeypatch):
    """La concurrencia mayor que uno ejecuta workers sin duplicar cola."""
    claimed = [[{"foto_id": 1}], [{"foto_id": 2}], [], []]
    processed: list[int] = []
    claim_lock = threading.Lock()

    def fake_claim_pending_photos(limit):
        """Entrega trabajos distintos a cada llamada simulada."""
        with claim_lock:
            if claimed:
                return claimed.pop(0)
            return []

    def fake_process_claimed_photo(photo):
        """Registra la tesela procesada."""
        processed.append(int(photo["foto_id"]))

    monkeypatch.setattr(
        worker_module, "claim_pending_photos", fake_claim_pending_photos
    )
    monkeypatch.setattr(
        worker_module, "_process_claimed_photo", fake_process_claimed_photo
    )

    count = worker_module.run_trace_worker_pool(
        app,
        once=True,
        batch_size=1,
        poll_seconds=0.01,
        worker_count=2,
    )

    assert count == 2
    assert sorted(processed) == [1, 2]


def test_traces_worker_command_uses_configured_concurrency(
    app, monkeypatch
):
    """El comando CLI respeta TRACE_WORKER_CONCURRENCY."""
    observed = {}

    def fake_run_trace_worker_pool(app_arg, **kwargs):
        """Registra la ejecución concurrente simulada."""
        observed["app"] = app_arg
        observed.update(kwargs)
        return 3

    monkeypatch.setattr(
        worker_module, "run_trace_worker_pool", fake_run_trace_worker_pool
    )
    app.config["TRACE_WORKER_CONCURRENCY"] = 2
    app.config["TRACE_WORKER_BATCH_SIZE"] = 1
    app.config["TRACE_WORKER_POLL_SECONDS"] = 0.5

    result = app.test_cli_runner().invoke(args=["traces-worker", "--once"])

    assert result.exit_code == 0
    assert observed["app"] is app
    assert observed["once"] is True
    assert observed["batch_size"] == 1
    assert observed["poll_seconds"] == 0.5
    assert observed["worker_count"] == 2
    assert "Fotos procesadas: 3" in result.output


def test_docker_compose_separates_web_and_worker():
    """Docker no debe arrancar workers internos en el servicio web."""
    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    web = compose["services"]["web"]
    worker = compose["services"]["worker"]

    assert web["environment"]["AUTO_START_TRACE_WORKER"] == "false"
    assert worker["environment"]["AUTO_START_TRACE_WORKER"] == "false"
    assert "ports" not in worker
    assert "gunicorn" not in " ".join(worker["command"])
    assert worker["command"] == [
        "flask",
        "--app",
        "run:app",
        "traces-worker",
    ]
