"""
===============================================================================
Pruebas de rutas complementarias de colección y galería.

Este módulo cubre ramas defensivas de helpers y rutas de colección que no
requieren modificar lógica de producción.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image
from werkzeug.exceptions import NotFound

from trazasytrazadas import collection as collection_module
from trazasytrazadas.collection_store import ZoneDeleteError


def _jpeg_bytes(size=(2, 2), color=(120, 130, 140)) -> bytes:
    """Construye una imagen JPEG mínima para los tests."""
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _photo(**overrides):
    """Construye los datos de una foto de colección."""
    payload = {
        "foto_id": 7,
        "parcela_id": 3,
        "tesela_id": "tile-7",
        "nombre_archivo": "tile_7.jpg",
        "ruta_foto": None,
        "ruta_trazas": None,
        "fuente_id": "pnoa",
        "limites_3857": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1},
        "ancho": 2,
        "alto": 2,
        "indice_fila": 0,
        "indice_columna": 0,
    }
    payload.update(overrides)
    return payload


def _zone(**overrides):
    """Construye los datos de una zona de colección."""
    payload = {
        "parcela_id": 3,
        "nombre_visible": "Zona prueba",
        "total_teselas": 1,
        "teselas_completadas": 0,
        "fotos": [_photo()],
    }
    payload.update(overrides)
    return payload


def test_collection_helpers_redirect_pagination_and_fallback_name(app):
    """Verifica las rutas de colección en el caso previsto."""
    assert (
        collection_module._safe_internal_redirect(None, "/fallback")
        == "/fallback"
    )
    assert (
        collection_module._safe_internal_redirect(
            "https://evil.test", "/fallback"
        )
        == "/fallback"
    )
    assert (
        collection_module._safe_internal_redirect("//evil.test/x", "/fallback")
        == "/fallback"
    )
    assert (
        collection_module._safe_internal_redirect("relative", "/fallback")
        == "/fallback"
    )
    assert (
        collection_module._safe_internal_redirect("/ok", "/fallback") == "/ok"
    )

    assert collection_module._pagination_items(1, 3) == [1, 2, 3]
    assert collection_module._pagination_items(5, 10) == [
        1,
        None,
        4,
        5,
        6,
        None,
        10,
    ]
    assert (
        collection_module._zone_download_filename(
            {"parcela_id": 42, "nombre_visible": ""}
        )
        == "parcela_42_tiles.zip"
    )


def test_load_zone_or_404_aborts_when_zone_is_missing(app, monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    monkeypatch.setattr(
        collection_module, "get_zone_detail", lambda parcel_id: None
    )

    with app.test_request_context("/"):
        with pytest.raises(NotFound):
            collection_module._load_zone_or_404(999)


def test_fetch_photo_bytes_uses_local_file_or_reports_missing_source(
    tmp_path, monkeypatch
):
    """Verifica que el comportamiento esperado informa el caso previsto."""
    local_file = tmp_path / "tile.jpg"
    local_file.write_bytes(b"local-bytes")
    monkeypatch.setattr(
        collection_module, "get_storage_abspath", lambda path: str(local_file)
    )

    assert (
        collection_module._fetch_photo_bytes(
            _photo(ruta_foto="tiles/tile.jpg")
        )
        == b"local-bytes"
    )

    monkeypatch.setattr(
        collection_module, "get_storage_abspath", lambda path: None
    )
    monkeypatch.setattr(
        collection_module, "_visor_source_by_id", lambda source_id: None
    )

    with pytest.raises(RuntimeError):
        collection_module._fetch_photo_bytes(_photo(fuente_id="missing"))


def test_fetch_photo_traces_reports_absent_missing_and_corrupt_files(
    tmp_path, monkeypatch
):
    """Verifica que el flujo de trazas informa el caso previsto."""
    monkeypatch.setattr(
        collection_module, "get_storage_abspath", lambda path: None
    )
    with pytest.raises(FileNotFoundError):
        collection_module._fetch_photo_traces(_photo(ruta_trazas=None))

    missing_file = tmp_path / "missing.json"
    monkeypatch.setattr(
        collection_module,
        "get_storage_abspath",
        lambda path: str(missing_file),
    )
    with pytest.raises(FileNotFoundError):
        collection_module._fetch_photo_traces(
            _photo(ruta_trazas="traces/missing.json")
        )

    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        collection_module,
        "get_storage_abspath",
        lambda path: str(corrupt_file),
    )
    with pytest.raises(ValueError):
        collection_module._fetch_photo_traces(
            _photo(ruta_trazas="traces/corrupt.json")
        )

    traces_file = tmp_path / "traces.json"
    traces_file.write_text(
        json.dumps({"xs": [1], "ys": [1]}), encoding="utf-8"
    )
    monkeypatch.setattr(
        collection_module, "get_storage_abspath", lambda path: str(traces_file)
    )
    assert collection_module._fetch_photo_traces(
        _photo(ruta_trazas="traces/traces.json")
    ) == {"xs": [1], "ys": [1]}


def test_render_overlay_and_zone_preview_special_cases(app, monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    photo = _photo(ruta_trazas="traces/tile.json")
    monkeypatch.setattr(
        collection_module, "_fetch_photo_bytes", lambda received: _jpeg_bytes()
    )
    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_traces",
        lambda received: {"xs": [0, 99], "ys": [0, 99]},
    )

    overlay = collection_module._render_photo_traces_overlay_png(photo)
    assert overlay.startswith(b"\x89PNG")

    with pytest.raises(RuntimeError):
        collection_module._build_zone_preview_bytes(_zone(fotos=[]))

    def failing_fetch(_photo):
        """Simula un fallo al obtener bytes de tesela."""
        raise RuntimeError("boom")

    monkeypatch.setattr(collection_module, "_fetch_photo_bytes", failing_fetch)
    with app.app_context(), pytest.raises(RuntimeError):
        collection_module._build_zone_preview_bytes(_zone())

    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_bytes",
        lambda received: _jpeg_bytes(size=(1, 1)),
    )
    preview = collection_module._build_zone_preview_bytes(
        _zone(fotos=[_photo(ancho=2, alto=2)])
    )
    assert preview.startswith(b"\xff\xd8")


def test_collection_listing_and_status_routes_parse_variants(
    client, force_login, monkeypatch
):
    """Verifica las rutas de colección en el caso previsto."""
    force_login()
    captured = {}

    def fake_list_zones(*, page, per_page, search):
        """Devuelve una lista simulada de zonas."""
        captured.update(page=page, per_page=per_page, search=search)
        return {"page": page, "total_pages": 10, "items": [], "total": 0}

    monkeypatch.setattr(collection_module, "list_zones", fake_list_zones)
    monkeypatch.setattr(
        collection_module,
        "render_template",
        lambda *args, **kwargs: "collection-ok",
    )

    response = client.get("/coleccion?page=nope&per_page=999&q= abc ")
    assert response.status_code == 200
    assert response.data == b"collection-ok"
    assert captured == {"page": 1, "per_page": 10, "search": "abc"}

    monkeypatch.setattr(
        collection_module,
        "list_zone_status_summaries",
        lambda ids: [{"ids": ids}],
    )
    response = client.get("/coleccion/status?ids=1,bad,2,2,-5,,3")
    assert response.get_json()["zonas"] == [{"ids": [1, 2, 3]}]

    monkeypatch.setattr(
        collection_module, "get_zone_live_status", lambda parcel_id: None
    )
    assert client.get("/coleccion/404/status").status_code == 404


def test_collection_preview_route_handles_generation_branches(
    client, force_login, tmp_path, monkeypatch
):
    """Verifica que las rutas de colección gestiona el caso previsto."""
    force_login()
    monkeypatch.setattr(
        collection_module,
        "get_zone_detail",
        lambda parcel_id: _zone(parcela_id=parcel_id),
    )

    existing = tmp_path / "preview.jpg"
    existing.write_bytes(_jpeg_bytes())
    monkeypatch.setattr(
        collection_module,
        "get_zone_preview_abspath",
        lambda parcel_id: str(existing),
    )
    response = client.get("/coleccion/3/preview")
    assert response.status_code == 200
    response.close()

    monkeypatch.setattr(
        collection_module.os.path, "exists", lambda path: False
    )
    monkeypatch.setattr(
        collection_module,
        "_build_zone_preview_bytes",
        lambda detail: (_ for _ in ()).throw(RuntimeError("no preview")),
    )
    response = client.get("/coleccion/3/preview")
    assert response.status_code == 502
    assert "no preview" in response.get_json()["error"]

    monkeypatch.setattr(
        collection_module,
        "_build_zone_preview_bytes",
        lambda detail: (_ for _ in ()).throw(ValueError("boom")),
    )
    assert client.get("/coleccion/3/preview").status_code == 502

    monkeypatch.setattr(
        collection_module,
        "_build_zone_preview_bytes",
        lambda detail: _jpeg_bytes(),
    )
    monkeypatch.setattr(
        collection_module,
        "save_zone_preview_bytes",
        lambda parcel_id, image_bytes: (_ for _ in ()).throw(OSError("disk")),
    )
    assert client.get("/coleccion/3/preview").status_code == 200

    saved = tmp_path / "saved.jpg"

    def save_preview(parcel_id, image_bytes):
        """Guarda una vista previa simulada en disco."""
        saved.write_bytes(image_bytes)
        return str(saved)

    monkeypatch.setattr(
        collection_module, "save_zone_preview_bytes", save_preview
    )
    response = client.get("/coleccion/3/preview")
    assert response.status_code == 200
    response.close()


def test_collection_download_rename_delete_and_retry_routes(
    client, force_login, monkeypatch
):
    """Verifica las rutas de colección en el caso previsto."""
    force_login()
    monkeypatch.setattr(
        collection_module,
        "get_zone_detail",
        lambda parcel_id: _zone(parcela_id=parcel_id, fotos=[]),
    )
    assert client.get("/coleccion/3/download-zip").status_code == 404

    monkeypatch.setattr(
        collection_module,
        "get_zone_detail",
        lambda parcel_id: _zone(parcela_id=parcel_id),
    )
    monkeypatch.setattr(
        collection_module,
        "update_zone_name",
        lambda parcel_id, name: (_ for _ in ()).throw(
            ValueError("nombre inválido")
        ),
    )
    response = client.post(
        "/coleccion/3/rename",
        data={"name": "x", "redirect_to": "https://evil.test"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/coleccion")

    monkeypatch.setattr(
        collection_module, "update_zone_name", lambda parcel_id, name: None
    )
    response = client.post(
        "/coleccion/3/rename",
        data={"name": "   ", "redirect_to": "/coleccion/3/galeria"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/coleccion/3/galeria")

    monkeypatch.setattr(
        collection_module,
        "delete_zone",
        lambda parcel_id: (_ for _ in ()).throw(ZoneDeleteError("no se pudo")),
    )
    assert (
        client.post(
            "/coleccion/3/delete", data={"redirect_to": "relative"}
        ).status_code
        == 302
    )

    monkeypatch.setattr(
        collection_module, "delete_zone", lambda parcel_id: False
    )
    assert client.post("/coleccion/3/delete").status_code == 302

    monkeypatch.setattr(
        collection_module, "zone_retry_is_enabled", lambda photos: False
    )
    monkeypatch.setattr(
        collection_module,
        "get_zone_detail",
        lambda parcel_id: _zone(total_teselas=1, teselas_completadas=1),
    )
    assert client.post("/coleccion/3/retry-pending-failed").status_code == 302

    monkeypatch.setattr(
        collection_module,
        "get_zone_detail",
        lambda parcel_id: _zone(total_teselas=1, teselas_completadas=0),
    )
    assert client.post("/coleccion/3/retry-pending-failed").status_code == 302

    monkeypatch.setattr(
        collection_module, "zone_retry_is_enabled", lambda photos: True
    )
    monkeypatch.setattr(
        collection_module, "retry_zone_pending_and_failed", lambda parcel_id: 0
    )
    assert client.post("/coleccion/3/retry-pending-failed").status_code == 302

    triggered = {"called": False}
    monkeypatch.setattr(
        collection_module, "retry_zone_pending_and_failed", lambda parcel_id: 2
    )
    monkeypatch.setattr(
        collection_module,
        "trigger_trace_worker",
        lambda app: triggered.update(called=True) or True,
    )
    assert client.post("/coleccion/3/retry-pending-failed").status_code == 302
    assert triggered["called"] is True


def test_collection_photo_retry_image_traces_and_download_routes(
    client, force_login, monkeypatch
):
    """Verifica las rutas de colección en el caso previsto."""
    force_login()
    monkeypatch.setattr(collection_module, "get_photo", lambda photo_id: None)
    assert client.post("/coleccion/fotos/404/retry").status_code == 404
    assert client.get("/coleccion/fotos/404/image").status_code == 404
    assert client.get("/coleccion/fotos/404/traces").status_code == 404
    assert client.get("/coleccion/fotos/404/download").status_code == 404

    photo = _photo()
    monkeypatch.setattr(collection_module, "get_photo", lambda photo_id: photo)
    monkeypatch.setattr(
        collection_module, "photo_retry_is_enabled", lambda received: False
    )
    assert client.post("/coleccion/fotos/7/retry").status_code == 302

    monkeypatch.setattr(
        collection_module, "photo_retry_is_enabled", lambda received: True
    )
    monkeypatch.setattr(
        collection_module, "retry_photo", lambda photo_id: None
    )
    monkeypatch.setattr(
        collection_module, "trigger_trace_worker", lambda app: True
    )
    assert client.post("/coleccion/fotos/7/retry").status_code == 302

    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_bytes",
        lambda received: (_ for _ in ()).throw(RuntimeError("sin fuente")),
    )
    assert client.get("/coleccion/fotos/7/image").status_code == 502
    assert client.get("/coleccion/fotos/7/download").status_code == 502

    monkeypatch.setattr(
        collection_module, "_fetch_photo_bytes", lambda received: _jpeg_bytes()
    )
    assert client.get("/coleccion/fotos/7/image").status_code == 200
    assert client.get("/coleccion/fotos/7/download").status_code == 200

    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_traces",
        lambda received: (_ for _ in ()).throw(
            FileNotFoundError("sin trazas")
        ),
    )
    assert client.get("/coleccion/fotos/7/traces").status_code == 404

    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_traces",
        lambda received: (_ for _ in ()).throw(ValueError("corrupto")),
    )
    assert client.get("/coleccion/fotos/7/traces").status_code == 500

    monkeypatch.setattr(
        collection_module,
        "_fetch_photo_traces",
        lambda received: {"xs": [0], "ys": [0]},
    )
    assert client.get("/coleccion/fotos/7/traces").get_json() == {
        "xs": [0],
        "ys": [0],
    }

    photo_with_traces = _photo(ruta_trazas="traces/tile.json")
    monkeypatch.setattr(
        collection_module, "get_photo", lambda photo_id: photo_with_traces
    )
    monkeypatch.setattr(
        collection_module,
        "_build_photo_download_zip",
        lambda received: (_ for _ in ()).throw(RuntimeError("sin fuente")),
    )
    assert client.get("/coleccion/fotos/7/download").status_code == 502

    monkeypatch.setattr(
        collection_module,
        "_build_photo_download_zip",
        lambda received: (_ for _ in ()).throw(
            FileNotFoundError("sin trazas")
        ),
    )
    assert client.get("/coleccion/fotos/7/download").status_code == 409

    monkeypatch.setattr(
        collection_module,
        "_build_photo_download_zip",
        lambda received: (b"zip-bytes", "tile_resultados.zip"),
    )
    assert client.get("/coleccion/fotos/7/download").status_code == 200
