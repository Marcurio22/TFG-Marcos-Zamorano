"""
===============================================================================
Pruebas de comportamiento de la capa de colección.

Este módulo cubre ramas defensivas de serialización, almacenamiento físico,
estados agregados, reintentos y borrado seguro de parcelas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

import trazasytrazadas.collection_store as store
from trazasytrazadas.db import db
from trazasytrazadas.models import Foto, Parcela


def _parcel(**overrides):
    """Construye una parcela mínima para persistencia."""
    payload = {
        "usuario_id": 1,
        "tamano_metros": 1.0,
        "pto_origen_latitud": 40.0,
        "pto_origen_longitud": -4.0,
        "pto_fin_latitud": 40.1,
        "pto_fin_longitud": -3.9,
        "fuente_id": "pnoa2023",
        "fuente_nombre": "PNOA 2023",
        "resolucion_solicitada": 0.25,
        "resolucion_real": 0.25,
        "ancho_tesela": 2,
        "alto_tesela": 2,
        "estado": "pending",
    }
    payload.update(overrides)
    return Parcela(**payload)


def _photo(parcel_id: int, **overrides):
    """Construye los datos de una foto de colección."""
    payload = {
        "parcela_id": parcel_id,
        "fecha_foto": "2026-05-14",
        "resolucion_valor": 0.25,
        "resolucion_unidad": "m/px",
        "longitud": -3.95,
        "latitud": 40.05,
        "ruta_foto": "/visor/download/tile?source_id=pnoa2023",
        "ruta_trazas": None,
        "trazas": 0,
        "estado": "pending",
        "mensaje_error": None,
        "iniciado_en": None,
        "finalizado_en": None,
        "numero_intentos": 0,
        "tesela_id": "r01_c01",
        "indice_fila": 1,
        "indice_columna": 1,
        "nombre_archivo": "tile.jpg",
        "ancho": 2,
        "alto": 2,
        "limites_3857_json": json.dumps(
            {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}
        ),
        "limites_json": json.dumps(
            {"sur": 40.0, "oeste": -4.0, "norte": 40.1, "este": -3.9}
        ),
    }
    payload.update(overrides)
    return Foto(**payload)


def _create_parcel_with_photos(app, *photo_statuses: str):
    """Crea una parcela con fotos asociadas."""
    with app.app_context():
        parcel = _parcel()
        db.session.add(parcel)
        db.session.flush()
        photos = []
        for index, status in enumerate(photo_statuses or ["pending"], start=1):
            photo = _photo(
                int(parcel.parcela_id),
                tesela_id=f"r01_c{index:02d}",
                indice_columna=index,
                estado=status,
                trazas=1 if status == "completed" else 0,
                ruta_trazas=(
                    f"parcelas/{parcel.parcela_id}/traces/tile_{index}.json"
                    if status == "completed"
                    else None
                ),
            )
            db.session.add(photo)
            photos.append(photo)
        db.session.commit()
        return int(parcel.parcela_id), [int(photo.foto_id) for photo in photos]


def test_collection_store_small_helpers_and_contracts(app):
    """Verifica la persistencia de colección en el caso previsto."""
    with app.app_context():
        assert store._date_from_db_timestamp(None)
        assert store._json_loads("", {"fallback": True}) == {"fallback": True}
        assert store._json_loads("{", []) == []
        assert store._bounds_to_spanish({}) == {}
        assert store._bounds_to_legacy({}) == {}
        assert store._tile_value({"es": 1}, "es", "legacy") == 1
        assert store._tile_value({"legacy": 2}, "es", "legacy") == 2
        assert (
            store._route_path_only("/visor/download/tile?a=1")
            == "/visor/download/tile?a=1"
        )
        assert store.get_default_user_id() == store.DEFAULT_SYSTEM_USER_ID
        assert store.list_zones()["zonas"] == []
        assert store.get_photo(1) is None
        assert store.delete_zone(1) is False
        assert store.get_zone_plan(1) is None
        assert store.get_zone_status_summary(1) is None
        assert store.get_zone_live_status(1) is None
        assert store.retry_zone_pending_and_failed(1) == 0
        assert store.retry_photo(1) is False
        assert store.mark_photo_completed(1, "missing.json") is None
        assert store.mark_photo_failed(1, "missing") is None
        assert store.refresh_parcel_status(1) == "pending"


def test_photo_retry_stale_and_zone_status_helpers(app):
    """Verifica el comportamiento esperado en el caso previsto."""
    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=300)).strftime("%Y-%m-%d %H:%M:%S")
    fresh = now.strftime("%Y-%m-%d %H:%M:%S")

    with app.app_context():
        app.config["COLLECTION_PHOTO_RETRY_ENABLE_SECONDS"] = 120
        app.config["TRACE_WORKER_STALE_SECONDS"] = 120
        assert store.photo_retry_is_enabled({"creado_en": None}) is True
        assert store.photo_retry_is_enabled({"creado_en": old}) is True
        assert store.photo_retry_is_enabled({"creado_en": fresh}) is False
        assert store._parse_db_timestamp("bad") is None
        assert (
            store._photo_is_stale({"estado": "processing", "iniciado_en": old})
            is True
        )
        assert (
            store._photo_is_stale(
                {"estado": "processing", "iniciado_en": "bad"}
            )
            is False
        )
        assert store._zone_photo_is_retryable({"estado": "failed"}) is True
        assert (
            store._zone_photo_is_retryable({"estado": "processing"}) is False
        )
        assert store._zone_trace_status([]) == "pending"
        assert store._zone_trace_status([{"estado": "failed"}]) == "failed"
        assert (
            store._zone_trace_status([{"estado": "processing"}])
            == "processing"
        )


def test_update_zone_name_missing_and_too_long_and_save_zone_invalid_status(
    app,
):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.test_request_context("/"):
        with pytest.raises(ValueError):
            store.update_zone_name(
                1, "x" * (store.COLLECTION_NAME_MAX_LENGTH + 1)
            )
        assert store.update_zone_name(999, "Nuevo nombre") is None
        with pytest.raises(ValueError):
            store.save_generated_zone(
                bbox4326=(40.0, -4.0, 40.1, -3.9),
                origin_point={"lat": 40.0, "lng": -4.0},
                destination_point={"lat": 40.1, "lng": -3.9},
                bbox3857=(0, 0, 1, 1),
                requested_resolution=0.25,
                actual_resolution=0.25,
                tile_width=2,
                tile_height=2,
                source={"id": "pnoa2023", "label": "PNOA"},
                tiles=[],
                status="unknown",
            )


def test_preview_staging_restore_and_purge_cleanup(app, tmp_path, monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.app_context():
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        preview_path = Path(store.save_zone_preview_bytes(3, b"preview"))
        assert preview_path.read_bytes() == b"preview"

        original_remove = os.remove
        original_replace = os.replace
        original_exists = os.path.exists
        removed = []

        def fake_replace(src, dst):
            """Simula el reemplazo atómico de archivos."""
            raise OSError("replace failed")

        def fake_exists(path):
            """Simula la existencia de rutas durante la prueba."""
            return str(path).endswith(".tmp") or Path(path).exists()

        def fake_remove(path):
            """Simula un error al eliminar archivos."""
            removed.append(path)
            raise OSError("remove failed")

        monkeypatch.setattr(store.os, "replace", fake_replace)
        monkeypatch.setattr(store.os.path, "exists", fake_exists)
        monkeypatch.setattr(store.os, "remove", fake_remove)
        with pytest.raises(OSError):
            store.save_zone_preview_bytes(4, b"preview")
        assert removed
        monkeypatch.setattr(store.os, "remove", original_remove)
        monkeypatch.setattr(store.os, "replace", original_replace)
        monkeypatch.setattr(store.os.path, "exists", original_exists)

        parcel_root = Path(store._parcel_root_dir(10))
        parcel_root.mkdir(parents=True)
        staged = store.stage_parcel_dirs_for_delete([10])
        assert staged[0][0] == str(parcel_root)
        assert Path(staged[0][1]).exists()

        monkeypatch.setattr(
            store.os,
            "replace",
            lambda src, dst: (_ for _ in ()).throw(OSError("restore failed")),
        )
        store.restore_staged_parcel_dirs(staged)

        monkeypatch.setattr(
            store.shutil,
            "rmtree",
            lambda path: (_ for _ in ()).throw(OSError("purge failed")),
        )
        store.purge_staged_parcel_dirs(staged)


def test_stage_parcel_dirs_restores_previous_staging_when_later_stage_fails(
    app, tmp_path, monkeypatch
):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.app_context():
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        first_root = Path(store._parcel_root_dir(1))
        first_root.mkdir(parents=True)
        calls = {"count": 0, "restored": None}
        original_stage = store._stage_parcel_dir_for_delete

        def fake_stage(parcel_id):
            """Simula un error al preparar el staging."""
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("boom")
            return original_stage(parcel_id)

        monkeypatch.setattr(store, "_stage_parcel_dir_for_delete", fake_stage)
        monkeypatch.setattr(
            store,
            "restore_staged_parcel_dirs",
            lambda staged: calls.update(restored=staged),
        )

        with pytest.raises(OSError):
            store.stage_parcel_dirs_for_delete([1, 2])
        assert calls["restored"]


def test_list_search_detail_plan_photo_and_materialize_paths(
    app, tmp_path, monkeypatch
):
    """Verifica el comportamiento esperado en el caso previsto."""
    parcel_id, photo_ids = _create_parcel_with_photos(
        app, "completed", "failed", "processing"
    )

    with app.test_request_context("/"):
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        listing = store.list_zones(page=1, per_page=10, search="pnoa")
        assert listing["total"] == 1
        detail = store.get_zone_detail(parcel_id)
        assert detail["total_teselas"] == 3
        assert detail["puede_reintentar_todo"] is True
        missing = store.get_photo(999999)
        assert missing is None

        import trazasytrazadas.visor as visor_module

        monkeypatch.setattr(
            visor_module, "_visor_source_by_id", lambda source_id: None
        )
        plan = store.get_zone_plan(parcel_id)
        assert plan["plan"]["fuente"]["servicio"] == "WMS"

        local_path = tmp_path / "local.jpg"
        local_path.write_bytes(b"image")
        photo = {"ruta_foto": store._relative_storage_path(str(local_path))}
        assert store.materialize_photo_tile(photo) == str(local_path)

        with pytest.raises(RuntimeError):
            store.materialize_photo_tile(
                {
                    "foto_id": photo_ids[0],
                    "parcela_id": parcel_id,
                    "fuente_id": "missing",
                    "limites_3857": {
                        "xmin": 0,
                        "ymin": 0,
                        "xmax": 1,
                        "ymax": 1,
                    },
                    "ancho": 2,
                    "alto": 2,
                    "nombre_archivo": "tile.jpg",
                    "ruta_foto": None,
                }
            )


def test_delete_zone_error_restore_and_purge_paths(app, tmp_path, monkeypatch):
    """Verifica el borrado en el caso previsto."""
    parcel_id, _photo_ids = _create_parcel_with_photos(app, "pending")

    with app.test_request_context("/"):
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        assert store.delete_zone(999999) is False

        staged = tmp_path / "staged"
        staged.mkdir()
        restored = []
        original_commit = db.session.commit
        monkeypatch.setattr(
            store,
            "_stage_parcel_dir_for_delete",
            lambda parcel_id: (str(tmp_path / "parcel"), str(staged)),
        )
        monkeypatch.setattr(
            store.os, "replace", lambda src, dst: restored.append((src, dst))
        )
        monkeypatch.setattr(
            db.session,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("db down")),
        )

        with pytest.raises(store.ZoneDeleteError):
            store.delete_zone(parcel_id)
        assert restored
        monkeypatch.setattr(db.session, "commit", original_commit)

    parcel_id, _photo_ids = _create_parcel_with_photos(app, "pending")
    with app.test_request_context("/"):
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        staged = tmp_path / "staged-ok"
        staged.mkdir(exist_ok=True)
        monkeypatch.setattr(
            store,
            "_stage_parcel_dir_for_delete",
            lambda parcel_id: (str(tmp_path / "parcel"), str(staged)),
        )
        monkeypatch.setattr(
            store.shutil,
            "rmtree",
            lambda path: (_ for _ in ()).throw(OSError("purge failed")),
        )
        assert store.delete_zone(parcel_id) is True


def test_mark_refresh_retry_and_remove_paths(app, tmp_path, monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    parcel_id, photo_ids = _create_parcel_with_photos(
        app, "pending", "failed", "completed"
    )

    with app.app_context():
        app.config["COLLECTION_STORAGE_ROOT"] = str(tmp_path)
        trace_path = tmp_path / "trace.json"
        trace_path.write_text("{}", encoding="utf-8")
        relative_trace_path = store._relative_storage_path(str(trace_path))
        photo = db.session.get(Foto, photo_ids[1])
        photo.ruta_trazas = relative_trace_path
        db.session.commit()

        monkeypatch.setattr(
            store.os,
            "remove",
            lambda path: (_ for _ in ()).throw(OSError("remove failed")),
        )
        assert store.retry_photo(photo_ids[1]) is True

        trace_path.write_text("{}", encoding="utf-8")
        photo = db.session.get(Foto, photo_ids[1])
        photo.estado = "failed"
        photo.ruta_trazas = relative_trace_path
        db.session.commit()
        assert store.retry_zone_pending_and_failed(parcel_id) >= 1
