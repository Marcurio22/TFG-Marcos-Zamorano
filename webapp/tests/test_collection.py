"""
Pruebas básicas de la colección de imágenes persistida en SQLite.

Estas pruebas validan el registro automático de zonas desde el visor, el
listado paginado, la vista de galería, la recuperación en el mapa y el
borrado en cascada de parcelas y fotos asociadas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""
import io
from PIL import Image

from trazasytrazadas import visor as visor_module
from trazasytrazadas.collection_store import (
    get_zone_detail,
    refresh_parcel_status,
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
    assert "Galería de la zona".encode("utf-8") in response.data
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
    assert "La tesela se ha marcado para recalcular la traza.".encode(
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
