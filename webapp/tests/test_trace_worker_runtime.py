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

import pytest

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
