"""
Pruebas del worker de trazas en segundo plano.

Validan que las teselas se persistan físicamente y que el worker CLI procese
fotos pendientes actualizando SQLite y guardando el resultado JSON.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io
import os
import pytest
import threading

from PIL import Image

from trazasytrazadas import trace_worker as worker_module
from trazasytrazadas import visor as visor_module
from trazasytrazadas.collection_store import (
    get_storage_abspath,
    refresh_parcel_status
)
from trazasytrazadas.db import db
from trazasytrazadas.models import Foto, Parcela


@pytest.fixture(autouse=True)
def _login_required_user(force_login):
    """Las pruebas del worker que tocan visor/colección
        se ejecutan autenticadas."""
    force_login(
        username="usuario_worker",
        email="usuario_worker@example.com",
    )


def _fake_jpeg_bytes() -> bytes:
    """Genera un JPEG mínimo válido para tests."""
    image = Image.new("RGB", (16, 16), color=(120, 70, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _register_zone(client, monkeypatch):
    """Genera una zona persistida usando el endpoint real del visor."""
    source = visor_module._visor_source_by_id("pnoa2023")

    monkeypatch.setattr(
        visor_module,
        "_visor_select_source",
        lambda _bbox, _resolution: (source, 0.25, []),
    )

    def _fake_tiles(_bbox, _resolution, _tile_width, _tile_height, _source):
        return (
            [
                {
                    "id": "r01_c01",
                    "row": 1,
                    "col": 1,
                    "filename": "tile_1.jpg",
                    "label": "Tesela 1-1",
                    "bounds": {
                        "south": 40.0,
                        "west": -4.0,
                        "north": 40.1,
                        "east": -3.9,
                    },
                    "bbox3857": {
                        "xmin": -1.0,
                        "ymin": -1.0,
                        "xmax": 1.0,
                        "ymax": 1.0,
                    },
                    "width": 1024,
                    "height": 640,
                    "download_url": "/visor/download/tile?source_id=pnoa2023",
                },
                {
                    "id": "r01_c02",
                    "row": 1,
                    "col": 2,
                    "filename": "tile_2.jpg",
                    "label": "Tesela 1-2",
                    "bounds": {
                        "south": 40.0,
                        "west": -3.9,
                        "north": 40.1,
                        "east": -3.8,
                    },
                    "bbox3857": {
                        "xmin": 1.0,
                        "ymin": -1.0,
                        "xmax": 2.0,
                        "ymax": 1.0,
                    },
                    "width": 1024,
                    "height": 640,
                    "download_url": "/visor/download/tile?source_id=pnoa2023",
                },
            ],
            1,
            2,
        )

    monkeypatch.setattr(visor_module, "_visor_build_tiles", _fake_tiles)
    monkeypatch.setattr(
        visor_module,
        "_visor_fetch_tile_bytes",
        lambda _source, _bbox, _width, _height: _fake_jpeg_bytes(),
    )

    response = client.post(
        "/visor/grid-plan",
        json={
            "bbox": {
                "south": 40.0,
                "west": -4.0,
                "north": 40.1,
                "east": -3.8,
            },
            "origin": {"lat": 40.123456, "lng": -3.654321},
            "destination": {"lat": 40.654321, "lng": -3.123456},
            "resolution": 0.25,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["parcel_id"] is not None
    return int(payload["parcel_id"])


def test_grid_plan_registers_pending_tiles_without_local_download(
    app, client, monkeypatch
):
    """Comprueba que grid-plan guarda metadata sin descargar teselas aún."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        photo = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.foto_id.asc())
            .limit(1)
        ).scalar_one()

        assert photo.estado == "pending"
        assert photo.trazas == 0
        assert photo.ruta_foto.startswith("/visor/download/tile")


def test_traces_worker_processes_pending_photos(app, client, monkeypatch):
    """Verifica que el worker procese fotos y guarde el resultado JSON."""
    parcel_id = _register_zone(client, monkeypatch)

    monkeypatch.setattr(
        worker_module,
        "compute_traces_from_segmentation",
        lambda **kwargs: {"xs": [1, 2, 3], "ys": [4, 5, 6]},
    )

    runner = app.test_cli_runner()
    result = runner.invoke(args=["traces-worker", "--once"])

    assert result.exit_code == 0

    with app.app_context():
        photo = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.foto_id.asc())
            .limit(1)
        ).scalar_one()

        parcel = db.session.get(Parcela, parcel_id)

        trace_absolute_path = get_storage_abspath(photo.ruta_trazas)
        assert photo.trazas == 1
        assert photo.estado == "completed"
        assert trace_absolute_path is not None
        assert os.path.exists(trace_absolute_path)
        assert parcel.estado == "completed"
        image_absolute_path = get_storage_abspath(photo.ruta_foto)
        assert image_absolute_path is not None
        assert os.path.exists(image_absolute_path)


def test_traces_worker_marks_failed_photos(app, client, monkeypatch):
    """Comprueba que el worker marque como fallida una foto con error."""
    parcel_id = _register_zone(client, monkeypatch)

    def _raise_error(**kwargs):
        raise RuntimeError("segmentation failed")

    monkeypatch.setattr(
        worker_module,
        "compute_traces_from_segmentation",
        _raise_error,
    )

    runner = app.test_cli_runner()
    result = runner.invoke(args=["traces-worker", "--once"])

    assert result.exit_code == 0

    with app.app_context():
        photo = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.foto_id.asc())
            .limit(1)
        ).scalar_one()

        parcel = db.session.get(Parcela, parcel_id)

        assert photo.estado == "failed"
        assert "segmentation failed" in (photo.error_message or "")
        assert photo.trazas == 0
        assert parcel.estado == "failed"


def test_collection_photo_retry_resets_failed_tile(app, client, monkeypatch):
    """Comprueba que una tesela fallida puede reintentarse manualmente."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        photo = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.foto_id.asc())
            .limit(1)
        ).scalar_one()

        photo_id = int(photo.foto_id)
        photo.estado = "failed"
        photo.error_message = "boom"
        photo.started_at = "2026-01-01 00:00:00"
        photo.finished_at = "2026-01-01 00:00:00"
        db.session.commit()
        refresh_parcel_status(parcel_id)

    response = client.post(
        f"/coleccion/fotos/{photo_id}/retry",
        data={"redirect_to": f"/coleccion/{parcel_id}/galeria"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "La tesela se ha marcado para recalcular las trazas.".encode(
        "utf-8"
    ) in response.data

    with app.app_context():
        photo = db.session.get(Foto, photo_id)

        assert photo.estado == "pending"
        assert photo.error_message is None
        assert photo.started_at is None
        assert photo.finished_at is None
        assert photo.ruta_trazas is None


def test_trigger_trace_worker_does_not_start_when_app_is_testing(
    app, monkeypatch
):
    """No debe arrancar ningún thread si la app está en modo testing."""
    app.config["AUTO_START_TRACE_WORKER"] = True
    created_threads = []

    class _UnexpectedThread:
        def __init__(self, *args, **kwargs):
            created_threads.append((args, kwargs))

        def start(self):
            created_threads.append("started")

        def is_alive(self):
            return False

    monkeypatch.setattr(worker_module.threading, "Thread", _UnexpectedThread)

    started = worker_module.trigger_trace_worker(app)

    assert started is False
    assert created_threads == []


def test_trigger_trace_worker_does_not_start_when_thread_is_alive(
    app, monkeypatch
):
    """No debe crear otro thread si ya hay uno vivo drenando la cola."""
    app.config["AUTO_START_TRACE_WORKER"] = True
    app.config["TESTING"] = False
    created_threads = []

    class _AliveThread:
        def is_alive(self):
            return True

    def _unexpected_thread(*args, **kwargs):
        created_threads.append((args, kwargs))
        raise AssertionError("No debería crearse un nuevo thread.")

    monkeypatch.setattr(worker_module.threading, "Thread", _unexpected_thread)

    app.extensions["trace_worker"] = {
        "lock": threading.Lock(),
        "thread": _AliveThread(),
    }

    started = worker_module.trigger_trace_worker(app)

    assert started is False
    assert created_threads == []
