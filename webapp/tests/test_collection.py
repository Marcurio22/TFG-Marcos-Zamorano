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
import pytest
import zipfile

from flask_login import login_user
from PIL import Image
from werkzeug.security import generate_password_hash

from trazasytrazadas import collection as collection_module
from trazasytrazadas import visor as visor_module
from trazasytrazadas.collection_store import (
    get_zone_detail,
    get_zone_plan,
    get_zone_preview_abspath,
    materialize_photo_tile,
    refresh_parcel_status,
    get_zone_live_status,
)
from trazasytrazadas.db import db
from trazasytrazadas.models import Foto, Parcela, Usuario


@pytest.fixture(autouse=True)
def _login_required_user(force_login):
    """Todas las pruebas de colección se ejecutan autenticadas."""
    force_login(
        username="usuario_coleccion",
        email="usuario_coleccion@example.com",
    )


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
                    "fila": 1,
                    "columna": 1,
                    "nombre_archivo": "tile_1.jpg",
                    "nombre": "Tesela 1-1",
                    "limites": {
                        "sur": 40.0,
                        "oeste": -4.0,
                        "norte": 40.1,
                        "este": -3.9,
                    },
                    "limites_3857": {
                        "xmin": -1.0,
                        "ymin": -1.0,
                        "xmax": 1.0,
                        "ymax": 1.0,
                    },
                    "ancho": 1024,
                    "alto": 640,
                    "url_descarga": "/visor/download/tile?fuente_id=pnoa2023",
                },
                {
                    "id": "r01_c02",
                    "fila": 1,
                    "columna": 2,
                    "nombre_archivo": "tile_2.jpg",
                    "nombre": "Tesela 1-2",
                    "limites": {
                        "sur": 40.0,
                        "oeste": -3.9,
                        "norte": 40.1,
                        "este": -3.8,
                    },
                    "limites_3857": {
                        "xmin": 1.0,
                        "ymin": -1.0,
                        "xmax": 2.0,
                        "ymax": 1.0,
                    },
                    "ancho": 1024,
                    "alto": 640,
                    "url_descarga": "/visor/download/tile?fuente_id=pnoa2023",
                },
            ],
            1,
            2,
        )

    monkeypatch.setattr(visor_module, "_visor_build_tiles", _fake_tiles)

    response = client.post(
        "/visor/grid-plan",
        json={
            "limites": {
                "sur": 40.0,
                "oeste": -4.0,
                "norte": 40.1,
                "este": -3.8,
            },
            "origen": {"lat": 40.123456, "lng": -3.654321},
            "destino": {"lat": 40.654321, "lng": -3.123456},
            "resolucion": 0.25,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["parcela_id"] is not None
    return int(payload["parcela_id"])


def _create_user(
    app,
    *,
    username: str,
    email: str,
) -> int:
    """Crea un usuario persistido para pruebas de colección."""
    with app.app_context():
        user = Usuario(
            nombre_usuario=username,
            correo_electronico=email,
            contrasena=generate_password_hash("Password1!"),
            rol="user",
        )
        db.session.add(user)
        db.session.commit()
        return int(user.usuario_id)


def _mark_photo_completed_with_traces(
    app,
    parcel_id,
    *,
    indice_fila=1,
    indice_columna=1,
    traces=None,
):
    """Asocia un JSON de trazas persistido a una tesela concreta."""
    if traces is None:
        traces = {"xs": [1, 2, 3], "ys": [4, 5, 6]}

    with app.app_context():
        photo = db.session.execute(
            db.select(Foto).where(
                Foto.parcela_id == parcel_id,
                Foto.indice_fila == indice_fila,
                Foto.indice_columna == indice_columna,
            )
        ).scalar_one_or_none()

        assert photo is not None

        filename_root, _extension = os.path.splitext(photo.nombre_archivo)
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

        photo.estado = "completed"
        photo.trazas = 1
        photo.ruta_trazas = relative_path
        db.session.commit()
        refresh_parcel_status(parcel_id)

        return int(photo.foto_id), photo.nombre_archivo, traces


def test_zone_plan_includes_trace_overlay_metadata(app, client, monkeypatch):
    """El plan restaurado incluye datos para pintar trazas en el visor."""
    parcel_id = _register_zone(client, monkeypatch)

    _mark_photo_completed_with_traces(
        app,
        parcel_id,
        indice_fila=1,
        indice_columna=1,
    )
    second_photo_id, _filename, _traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
        indice_fila=1,
        indice_columna=2,
    )

    with app.test_request_context("/visor"):
        parcel = db.session.get(Parcela, parcel_id)
        assert parcel is not None

        owner = db.session.get(Usuario, int(parcel.usuario_id))
        assert owner is not None

        login_user(owner)
        plan = get_zone_plan(parcel_id)

    assert plan is not None
    assert plan["estado_trazas"] == "completed"
    assert plan["puede_dibujar_trazas"] is True
    assert plan["plan"]["estado_trazas"] == "completed"
    assert plan["plan"]["puede_dibujar_trazas"] is True

    tile = plan["plan"]["teselas"][1]
    assert tile["foto_id"] == second_photo_id
    assert tile["estado_trazas"] == "completed"
    assert tile["url_trazas"].endswith(
        f"/coleccion/fotos/{second_photo_id}/traces")


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
        parcel_count = db.session.execute(
            db.select(db.func.count(Parcela.parcela_id))
        ).scalar_one()
        photo_count = db.session.execute(
            db.select(db.func.count(Foto.foto_id)).where(
                Foto.parcela_id == parcel_id
            )
        ).scalar_one()

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
    assert b"zonaInicial" in response.data

    with app.app_context():
        detail = get_zone_detail(parcel_id)
        assert detail is not None
        assert detail["total_teselas"] == 2


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
        parcel_count = db.session.execute(
            db.select(db.func.count(Parcela.parcela_id)).where(
                Parcela.parcela_id == parcel_id
            )
        ).scalar_one()
        photo_count = db.session.execute(
            db.select(db.func.count(Foto.foto_id)).where(
                Foto.parcela_id == parcel_id
            )
        ).scalar_one()

    assert parcel_count == 0
    assert photo_count == 0


def test_collection_delete_removes_zone_storage(app, client, monkeypatch):
    """Comprueba que el borrado también elimina la carpeta física."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        detail = get_zone_detail(parcel_id)
        assert detail is not None
        assert detail["fotos"]

        first_photo = detail["fotos"][0]
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
    assert "zonas" in payload
    assert len(payload["zonas"]) == 1
    zone = payload["zonas"][0]
    assert zone["parcela_id"] == parcel_id
    assert zone["estado"] == "pending"
    assert zone["total_teselas"] == 2
    assert zone["teselas_completadas"] == 0


def test_collection_zone_status_endpoint_returns_photo_states(
    app, client, monkeypatch
):
    """Comprueba el endpoint JSON detallado de una zona y sus fotos."""
    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        processing_photo = db.session.execute(
            db.select(Foto).where(
                Foto.parcela_id == parcel_id,
                Foto.indice_fila == 1,
                Foto.indice_columna == 1,
            )
        ).scalar_one()
        completed_photo = db.session.execute(
            db.select(Foto).where(
                Foto.parcela_id == parcel_id,
                Foto.indice_fila == 1,
                Foto.indice_columna == 2,
            )
        ).scalar_one()
        processing_photo.estado = "processing"
        completed_photo.estado = "completed"
        completed_photo.trazas = 1
        db.session.commit()
        refresh_parcel_status(parcel_id)

    response = client.get(f"/coleccion/{parcel_id}/status")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["parcela_id"] == parcel_id
    assert payload["estado"] == "processing"
    assert payload["total_teselas"] == 2
    assert payload["teselas_completadas"] == 1
    assert payload["teselas_procesando"] == 1
    assert len(payload["fotos"]) == 2
    assert payload["fotos"][0]["estado"] == "processing"
    assert payload["fotos"][1]["estado"] == "completed"


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
        photo.mensaje_error = "boom"
        photo.iniciado_en = "2026-01-01 00:00:00"
        photo.finalizado_en = "2026-01-01 00:00:00"
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
        assert photo.mensaje_error is None
        assert photo.iniciado_en is None
        assert photo.finalizado_en is None
        assert photo.ruta_trazas is None


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
        assert detail["nombre_visible"] == "Parcela norte"


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
        indice_fila=1,
        indice_columna=2,
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
        indice_fila=1,
        indice_columna=1,
    )

    response = client.post(
        f"/coleccion/{parcel_id}/retry-pending-failed",
        data={"redirect_to": f"/coleccion/{parcel_id}/galeria"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        rows = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.indice_fila.asc(), Foto.indice_columna.asc())
        ).scalars().all()

        assert len(rows) == 2

        assert rows[0].foto_id == completed_photo_id
        assert rows[0].estado == "completed"
        assert rows[0].ruta_trazas is not None

        assert rows[1].estado == "pending"
        assert rows[1].mensaje_error is None
        assert rows[1].ruta_trazas is None


def test_collection_zone_retry_failed_only_skips_completed(
    app, client, monkeypatch
):
    """El recálculo masivo resetea failed, pero mantiene completed."""
    parcel_id = _register_zone(client, monkeypatch)

    completed_photo_id, _filename, _traces = _mark_photo_completed_with_traces(
        app,
        parcel_id,
        indice_fila=1,
        indice_columna=1,
    )
    failed_photo_id, failed_filename, failed_traces = (
        _mark_photo_completed_with_traces(
            app,
            parcel_id,
            indice_fila=1,
            indice_columna=2,
            traces={"xs": [7, 8], "ys": [9, 10]},
        )
    )

    with app.app_context():
        failed_photo = db.session.get(Foto, failed_photo_id)
        failed_photo.estado = "failed"
        failed_photo.mensaje_error = "boom"
        failed_photo.iniciado_en = "2026-01-01 00:00:00"
        failed_photo.finalizado_en = "2026-01-01 00:00:00"
        db.session.commit()
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
        rows = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.indice_fila.asc(), Foto.indice_columna.asc())
        ).scalars().all()

        assert len(rows) == 2

        assert rows[0].foto_id == completed_photo_id
        assert rows[0].estado == "completed"
        assert rows[0].ruta_trazas is not None

        assert rows[1].foto_id == failed_photo_id
        assert rows[1].estado == "pending"
        assert rows[1].mensaje_error is None
        assert rows[1].iniciado_en is None
        assert rows[1].finalizado_en is None
        assert rows[1].ruta_trazas is None

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

    _mark_photo_completed_with_traces(
        app, parcel_id, indice_fila=1, indice_columna=1)
    _mark_photo_completed_with_traces(
        app, parcel_id, indice_fila=1, indice_columna=2)

    with app.app_context():
        payload = get_zone_live_status(parcel_id)
        assert payload is not None
        assert payload["estado"] == "completed"
        assert payload["puede_reintentar_todo"] is False


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
        photo = db.session.execute(
            db.select(Foto)
            .where(Foto.parcela_id == parcel_id)
            .order_by(Foto.foto_id.asc())
            .limit(1)
        ).scalar_one()

        photo_id = int(photo.foto_id)
        photo.estado = "failed"
        photo.mensaje_error = "boom"
        photo.iniciado_en = "2026-01-01 00:00:00"
        photo.finalizado_en = "2026-01-01 00:00:00"
        db.session.commit()
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


def test_grid_plan_registers_zone_for_authenticated_user(
    app,
    client,
    monkeypatch,
):
    """Una zona nueva se asocia al usuario autenticado."""
    user_id = _create_user(
        app,
        username="Vindi22",
        email="vindi@example.com",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    parcel_id = _register_zone(client, monkeypatch)

    with app.app_context():
        parcel = db.session.get(Parcela, parcel_id)
        assert parcel is not None
        owner_id = parcel.usuario_id

    assert owner_id == user_id


def test_anonymous_user_cannot_create_zone_from_visor(client):
    """El usuario anónimo no puede crear zonas desde el visor."""
    with client.session_transaction() as session:
        session.clear()

    response = client.post(
        "/visor/grid-plan",
        json={
            "limites": {
                "sur": 40.0,
                "oeste": -4.0,
                "norte": 40.1,
                "este": -3.8,
            },
            "origen": {"lat": 40.123456, "lng": -3.654321},
            "destino": {"lat": 40.654321, "lng": -3.123456},
            "resolucion": 0.25,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_collection_gallery_returns_404_for_foreign_zone(
    app,
    client,
    monkeypatch,
):
    """Un usuario no puede abrir la galería de una zona ajena."""
    owner_id = _create_user(
        app,
        username="Vindi22",
        email="vindi@example.com",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    parcel_id = _register_zone(client, monkeypatch)

    with client.session_transaction() as session:
        session.clear()

    other_id = _create_user(
        app,
        username="Pepe1234",
        email="pepe@example.com",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(other_id)
        session["_fresh"] = True

    response = client.get(f"/coleccion/{parcel_id}/galeria")
    assert response.status_code == 404


def test_anonymous_collection_redirects_to_login(client):
    """La colección exige autenticación para usuarios anónimos."""
    with client.session_transaction() as session:
        session.clear()

    response = client.get("/coleccion", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
