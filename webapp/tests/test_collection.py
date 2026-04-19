"""
Pruebas básicas de la colección de imágenes persistida en SQLite.

Estas pruebas validan el registro automático de zonas desde el visor, el
listado paginado, la vista de galería, la recuperación en el mapa y el
borrado en cascada de parcelas y fotos asociadas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""
import io
import json
import os
import zipfile

from PIL import Image

from trazasytrazadas import collection as collection_module
from trazasytrazadas import visor as visor_module
from trazasytrazadas.collection_store import (
    get_zone_detail,
    get_zone_preview_abspath,
    materialize_photo_tile,
    refresh_parcel_status,
    get_zone_live_status,
)
from trazasytrazadas.db import get_db


def _fake_jpeg_bytes() -> bytes:
    """Genera un JPEG mínimo válido para la persistencia local de teselas."""
    image = Image.new("RGB", (16, 16), color=(35, 90, 160))
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

    monkeypatch.setattr(
        visor_module,
        "_visor_fetch_tile_bytes",
        lambda _source, _bbox, _width, _height: _fake_jpeg_bytes(),
    )
    monkeypatch.setattr(
        collection_module,
        "_visor_fetch_tile_bytes",
        lambda _source, _bbox, _width, _height: _fake_jpeg_bytes(),
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


def _mark_photo_completed_with_traces(
    app,
    parcel_id,
    *,
    row_index=1,
    col_index=1,
    traces=None,
):
    """Asocia un JSON de trazas persistido a una tesela concreta."""
    if traces is None:
        traces = {"xs": [1, 2, 3], "ys": [4, 5, 6]}

    with app.app_context():
        database = get_db()
        photo_row = database.execute(
            """
            SELECT foto_id, filename
            FROM foto
            WHERE parcela_id = ?
              AND row_index = ?
              AND col_index = ?
            """,
            (parcel_id, row_index, col_index),
        ).fetchone()

        assert photo_row is not None

        filename_root, _extension = os.path.splitext(photo_row["filename"])
        relative_path = (
            f"parcelas/{parcel_id}/traces/{filename_root}_traces.json"
        )
        absolute_path = os.path.join(
            app.config["COLLECTION_STORAGE_ROOT"],
            relative_path,
        )
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

        with open(absolute_path, "w", encoding="utf-8") as traces_file:
            json.dump(traces, traces_file, ensure_ascii=False, indent=2)

        database.execute(
            """
            UPDATE foto
            SET
                estado = 'completed',
                trazas = 1,
                ruta_trazas = ?
            WHERE foto_id = ?
            """,
            (relative_path, photo_row["foto_id"]),
        )
        database.commit()
        refresh_parcel_status(parcel_id)

        return int(photo_row["foto_id"]), photo_row["filename"], traces


def test_collection_page_renders_empty_state(client):
    """Comprueba el acceso a la nueva ruta principal de colección."""
    response = client.get("/coleccion")
    assert response.status_code == 200
    assert "Colección de imágenes".encode("utf-8") in response.data
    assert b"window.COLLECTION_APP" in response.data


def test_grid_plan_registers_zone_in_sqlite(app, client, monkeypatch):
    """Verifica el alta automática de una zona al generar la cuadrícula."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        database = get_db()
        parcel_count = database.execute(
            "SELECT COUNT(*) AS total FROM parcela"
        ).fetchone()["total"]
        photo_count = database.execute(
            "SELECT COUNT(*) AS total FROM foto WHERE parcela_id = ?",
            (parcel_id,),
        ).fetchone()["total"]

    assert parcel_count == 1
    assert photo_count == 2

    listing = client.get("/coleccion")
    assert listing.status_code == 200
    assert b"40.123456" in listing.data
    assert b"40.654321" in listing.data
    assert b"PNOA 2023" in listing.data


def test_collection_gallery_route_renders_saved_tiles(client, monkeypatch):
    """Comprueba que la galería mínima es accesible para una zona guardada."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.get(f"/coleccion/{parcel_id}/galeria")
    assert response.status_code == 200
    assert "Teselas guardadas a partir de la cuadrícula "
    "generada en el visor.".encode(
        "utf-8"
    ) in response.data
    assert b"tile_1.jpg" in response.data
    assert b"tile_2.jpg" in response.data


def test_visor_can_restore_zone_from_collection(app, client, monkeypatch):
    """Verifica que el visor pueda reabrirse con una zona persistida."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.get(f"/visor?parcel_id={parcel_id}")
    assert response.status_code == 200
    assert b"initialZone" in response.data

    with app.app_context():
        detail = get_zone_detail(parcel_id)
        assert detail is not None
        assert detail["tile_count"] == 2


def test_collection_delete_removes_zone_and_photos(app, client, monkeypatch):
    """Comprueba el borrado permanente y en cascada de la zona."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.post(
        f"/coleccion/{parcel_id}/delete",
        data={"redirect_to": "/coleccion"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "La zona se ha eliminado correctamente.".encode(
        "utf-8") in response.data

    with app.app_context():
        database = get_db()
        parcel_count = database.execute(
            "SELECT COUNT(*) AS total FROM parcela WHERE parcela_id = ?",
            (parcel_id,),
        ).fetchone()["total"]
        photo_count = database.execute(
            "SELECT COUNT(*) AS total FROM foto WHERE parcela_id = ?",
            (parcel_id,),
        ).fetchone()["total"]

    assert parcel_count == 0
    assert photo_count == 0


def test_collection_delete_removes_zone_storage(app, client, monkeypatch):
    """Comprueba que el borrado también elimina la carpeta física."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        detail = get_zone_detail(parcel_id)
        assert detail is not None
        assert detail["photos"]

        first_photo = detail["photos"][0]
        tile_path = materialize_photo_tile(first_photo)
        assert os.path.exists(tile_path)

        parcel_root = os.path.join(
            app.config["COLLECTION_STORAGE_ROOT"],
            "parcelas",
            str(parcel_id),
        )
        assert os.path.isdir(parcel_root)

    response = client.post(
        f"/coleccion/{parcel_id}/delete",
        data={"redirect_to": "/coleccion"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        parcel_root = os.path.join(
            app.config["COLLECTION_STORAGE_ROOT"],
            "parcelas",
            str(parcel_id),
        )
        assert not os.path.exists(parcel_root)


def test_collection_status_endpoint_returns_zone_summary(app,
                                                         client, monkeypatch):
    """Comprueba el endpoint JSON resumido de estados de colección."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.get(f"/coleccion/status?ids={parcel_id}")
    assert response.status_code == 200

    payload = response.get_json()
    assert "zones" in payload
    assert len(payload["zones"]) == 1
    zone = payload["zones"][0]
    assert zone["parcela_id"] == parcel_id
    assert zone["estado"] == "pending"
    assert zone["tile_count"] == 2
    assert zone["completed_tiles"] == 0


def test_collection_zone_status_endpoint_returns_photo_states(
    app, client, monkeypatch
):
    """Comprueba el endpoint JSON detallado de una zona y sus fotos."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        database = get_db()
        database.execute(
            """
            UPDATE foto
            SET estado = 'processing'
            WHERE parcela_id = ?
              AND row_index = 1
              AND col_index = 1
            """,
            (parcel_id,),
        )
        database.execute(
            """
            UPDATE foto
            SET estado = 'completed', trazas = 1
            WHERE parcela_id = ?
              AND row_index = 1
              AND col_index = 2
            """,
            (parcel_id,),
        )
        database.commit()
        refresh_parcel_status(parcel_id)

    response = client.get(f"/coleccion/{parcel_id}/status")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["parcela_id"] == parcel_id
    assert payload["estado"] == "processing"
    assert payload["tile_count"] == 2
    assert payload["completed_tiles"] == 1
    assert payload["processing_tiles"] == 1
    assert len(payload["photos"]) == 2
    assert payload["photos"][0]["estado"] == "processing"
    assert payload["photos"][1]["estado"] == "completed"


def test_collection_photo_retry_resets_failed_tile(app, client, monkeypatch):
    """Comprueba que una tesela fallida puede reintentarse manualmente."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        database = get_db()
        photo_row = database.execute(
            """
            SELECT foto_id
            FROM foto
            WHERE parcela_id = ?
            ORDER BY foto_id ASC
            LIMIT 1
            """,
            (parcel_id,),
        ).fetchone()

        photo_id = int(photo_row["foto_id"])

        database.execute(
            """
            UPDATE foto
            SET
                estado = 'failed',
                error_message = 'boom',
                started_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP
            WHERE foto_id = ?
            """,
            (photo_id,),
        )
        database.commit()
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
        database = get_db()
        row = database.execute(
            """
            SELECT estado, error_message, started_at, finished_at, ruta_trazas
            FROM foto
            WHERE foto_id = ?
            """,
            (photo_id,),
        ).fetchone()

        assert row["estado"] == "pending"
        assert row["error_message"] is None
        assert row["started_at"] is None
        assert row["finished_at"] is None
        assert row["ruta_trazas"] is None


def test_collection_zone_rename_updates_db_and_gallery_title(
    app, client, monkeypatch
):
    """Comprueba que una colección puede renombrarse y verse en galería."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.post(
        f"/coleccion/{parcel_id}/rename",
        data={
            "name": "Parcela norte",
            "redirect_to": f"/coleccion/{parcel_id}/galeria",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Parcela norte" in response.data

    with app.app_context():
        detail = get_zone_detail(parcel_id)
        assert detail is not None
        assert detail["nombre_coleccion"] == "Parcela norte"
        assert detail["display_name"] == "Parcela norte"


def test_collection_photo_traces_endpoint_returns_json(
    app, client, monkeypatch
):
    """Comprueba que una tesela completada expone su JSON de trazas."""
    parcel_id = _register_zone(client, monkeypatch)
    photo_id, _filename, traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
    )

    response = client.get(f"/coleccion/fotos/{photo_id}/traces")
    assert response.status_code == 200
    assert response.get_json() == traces


def test_collection_photo_download_returns_zip_when_traces_exist(
    app, client, monkeypatch
):
    """Descarga un ZIP con imagen, JSON y overlay
        si la tesela ya tiene trazas."""
    parcel_id = _register_zone(client, monkeypatch)
    _photo_id, filename, traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
    )

    response = client.get(f"/coleccion/fotos/{_photo_id}/download")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"

    filename_root, extension = os.path.splitext(filename)
    with zipfile.ZipFile(io.BytesIO(response.data), "r") as archive:
        names = set(archive.namelist())
        assert names == {
            f"input/{filename_root}{extension}",
            f"output/{filename_root}_traces.json",
            f"output/{filename_root}_traces.png",
        }
        assert json.loads(
            archive.read(f"output/{filename_root}_traces.json").decode("utf-8")
        ) == traces
        assert archive.read(f"output/{filename_root}_traces.png").startswith(
            b"\x89PNG\r\n\x1a\n"
        )


def test_collection_download_zip_includes_traces_artifacts(
    app, client, monkeypatch
):
    """El ZIP de la galería incluye artefactos
        extra para teselas completadas."""
    parcel_id = _register_zone(client, monkeypatch)
    photo_id, filename, traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
        row_index=1,
        col_index=2,
    )

    response = client.get(f"/coleccion/{parcel_id}/download-zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"

    filename_root, extension = os.path.splitext(filename)
    with zipfile.ZipFile(io.BytesIO(response.data), "r") as archive:
        names = set(archive.namelist())
        assert "input/tile_1.jpg" in names
        assert "input/tile_2.jpg" in names
        assert f"output/{filename_root}_traces.json" in names
        assert f"output/{filename_root}_traces.png" in names
        assert "log.json" in names
        assert json.loads(
            archive.read(f"output/{filename_root}_traces.json").decode("utf-8")
        ) == traces
        assert archive.read(f"output/{filename_root}_traces.png").startswith(
            b"\x89PNG\r\n\x1a\n"
        )


def test_collection_download_zip_uses_collection_name(
    app, client, monkeypatch
):
    """El ZIP de zona usa el nombre visible de la colección cuando existe."""
    parcel_id = _register_zone(client, monkeypatch)

    rename_response = client.post(
        f"/coleccion/{parcel_id}/rename",
        data={
            "name": "Ondas",
            "redirect_to": f"/coleccion/{parcel_id}/galeria",
        },
        follow_redirects=True,
    )
    assert rename_response.status_code == 200

    response = client.get(f"/coleccion/{parcel_id}/download-zip")
    assert response.status_code == 200
    assert (
        'filename=Ondas_tiles.zip'
        in response.headers["Content-Disposition"]
    )


def test_collection_zone_retry_pending_only_skips_completed(
    app, client, monkeypatch
):
    """El recálculo masivo toca pending, pero no invalida completed."""
    app.config["COLLECTION_PHOTO_RETRY_ENABLE_SECONDS"] = 0
    parcel_id = _register_zone(client, monkeypatch)

    completed_photo_id, _filename, _traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
        row_index=1,
        col_index=1,
    )

    response = client.post(
        f"/coleccion/{parcel_id}/retry-pending-failed",
        data={"redirect_to": f"/coleccion/{parcel_id}/galeria"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        database = get_db()
        rows = database.execute(
            """
            SELECT foto_id, estado, error_message, ruta_trazas
            FROM foto
            WHERE parcela_id = ?
            ORDER BY row_index ASC, col_index ASC
            """,
            (parcel_id,),
        ).fetchall()

        assert len(rows) == 2

        assert rows[0]["foto_id"] == completed_photo_id
        assert rows[0]["estado"] == "completed"
        assert rows[0]["ruta_trazas"] is not None

        assert rows[1]["estado"] == "pending"
        assert rows[1]["error_message"] is None
        assert rows[1]["ruta_trazas"] is None


def test_collection_zone_retry_failed_only_skips_completed(
    app, client, monkeypatch
):
    """El recálculo masivo resetea failed, pero mantiene completed."""
    parcel_id = _register_zone(client, monkeypatch)

    completed_photo_id, _filename, _traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
        row_index=1,
        col_index=1,
    )
    failed_photo_id, failed_filename, failed_traces = (
        _mark_photo_completed_with_traces(
            app,
            parcel_id,
            row_index=1,
            col_index=2,
            traces={"xs": [7, 8], "ys": [9, 10]},
        )
    )

    with app.app_context():
        database = get_db()
        database.execute(
            """
            UPDATE foto
            SET
                estado = 'failed',
                error_message = 'boom',
                started_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP
            WHERE foto_id = ?
            """,
            (failed_photo_id,),
        )
        database.commit()
        refresh_parcel_status(parcel_id)

        failed_filename_root, _extension = os.path.splitext(failed_filename)
        failed_trace_path = os.path.join(
            app.config["COLLECTION_STORAGE_ROOT"],
            "parcelas",
            str(parcel_id),
            "traces",
            f"{failed_filename_root}_traces.json",
        )
        assert os.path.exists(failed_trace_path)

    response = client.post(
        f"/coleccion/{parcel_id}/retry-pending-failed",
        data={"redirect_to": f"/coleccion/{parcel_id}/galeria"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        database = get_db()
        rows = database.execute(
            """
            SELECT foto_id, estado, error_message, started_at,
                finished_at, ruta_trazas
            FROM foto
            WHERE parcela_id = ?
            ORDER BY row_index ASC, col_index ASC
            """,
            (parcel_id,),
        ).fetchall()

        assert len(rows) == 2

        assert rows[0]["foto_id"] == completed_photo_id
        assert rows[0]["estado"] == "completed"
        assert rows[0]["ruta_trazas"] is not None

        assert rows[1]["foto_id"] == failed_photo_id
        assert rows[1]["estado"] == "pending"
        assert rows[1]["error_message"] is None
        assert rows[1]["started_at"] is None
        assert rows[1]["finished_at"] is None
        assert rows[1]["ruta_trazas"] is None

        failed_filename_root, _extension = os.path.splitext(failed_filename)
        failed_trace_path = os.path.join(
            app.config["COLLECTION_STORAGE_ROOT"],
            "parcelas",
            str(parcel_id),
            "traces",
            f"{failed_filename_root}_traces.json",
        )
        assert not os.path.exists(failed_trace_path)


def test_collection_zone_status_disables_bulk_retry_when_completed(
    app, client, monkeypatch
):
    """La galería no habilita el botón si toda la zona está completada."""
    parcel_id = _register_zone(client, monkeypatch)

    _mark_photo_completed_with_traces(app, parcel_id, row_index=1, col_index=1)
    _mark_photo_completed_with_traces(app, parcel_id, row_index=1, col_index=2)

    with app.app_context():
        payload = get_zone_live_status(parcel_id)
        assert payload is not None
        assert payload["estado"] == "completed"
        assert payload["can_retry_all"] is False


def test_collection_preview_persists_file_on_first_request(
    app, client, monkeypatch
):
    """La primera llamada de preview guarda el JPEG persistido en disco."""
    parcel_id = _register_zone(client, monkeypatch)

    response = client.get(f"/coleccion/{parcel_id}/preview")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"

    with app.app_context():
        preview_path = get_zone_preview_abspath(parcel_id)
        assert os.path.exists(preview_path)

        with open(preview_path, "rb") as preview_file:
            assert preview_file.read(3) == b"\xff\xd8\xff"


def test_collection_preview_reuses_persisted_file(
    app, client, monkeypatch
):
    """Una preview ya persistida se reutiliza sin reconstruirse."""
    parcel_id = _register_zone(client, monkeypatch)

    first_response = client.get(f"/coleccion/{parcel_id}/preview")
    assert first_response.status_code == 200

    def _fail_if_rebuilt(_detail):
        raise AssertionError("La preview no debería reconstruirse.")

    monkeypatch.setattr(
        collection_module,
        "_build_zone_preview_bytes",
        _fail_if_rebuilt,
    )

    second_response = client.get(f"/coleccion/{parcel_id}/preview")
    assert second_response.status_code == 200
    assert second_response.mimetype == "image/jpeg"


def test_collection_photo_retry_triggers_worker(app, client, monkeypatch):
    """El retry manual de una tesela debe disparar el worker bajo demanda."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        database = get_db()
        photo_row = database.execute(
            """
            SELECT foto_id
            FROM foto
            WHERE parcela_id = ?
            ORDER BY foto_id ASC
            LIMIT 1
            """,
            (parcel_id,),
        ).fetchone()

        photo_id = int(photo_row["foto_id"])

        database.execute(
            """
            UPDATE foto
            SET
                estado = 'failed',
                error_message = 'boom',
                started_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP
            WHERE foto_id = ?
            """,
            (photo_id,),
        )
        database.commit()
        refresh_parcel_status(parcel_id)

    triggered = []

    monkeypatch.setattr(
        collection_module,
        "trigger_trace_worker",
        lambda app_obj: triggered.append(app_obj) or True,
    )

    response = client.post(
        f"/coleccion/fotos/{photo_id}/retry",
        data={"redirect_to": f"/coleccion/{parcel_id}/galeria"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(triggered) == 1
    assert triggered[0] is app
