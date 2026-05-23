"""
===============================================================================
Pruebas de rutas y validaciones del visor cartográfico.

Este módulo cubre validaciones, utilidades WMS y selección de fuentes
sin depender de servicios externos.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO
import json
import zipfile
from urllib.error import HTTPError, URLError

import pytest
from PIL import Image

import trazasytrazadas.visor as visor


def _jpeg_bytes(color=(120, 80, 40), size=(24, 24)) -> bytes:
    """Construye una imagen JPEG mínima para los tests."""
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _varied_jpeg_bytes() -> bytes:
    """Construye una imagen JPEG no uniforme."""
    image = Image.new("RGB", (24, 24))
    for x in range(24):
        for y in range(24):
            image.putpixel(
                (x, y), ((x * 11) % 255, (y * 13) % 255, ((x + y) * 7) % 255)
            )
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_rgba_bytes(alpha=0) -> bytes:
    """Construye una imagen PNG con canal alfa."""
    buffer = BytesIO()
    Image.new("RGBA", (8, 8), color=(255, 0, 0, alpha)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def test_public_contract_helpers_and_bbox_validation(app):
    """Verifica las validaciones en el caso previsto."""
    source = visor.VISOR_PNOA_SOURCES[0]
    assert visor._visor_source_by_id(source["id"]) is source
    assert visor._visor_source_by_id("missing") is None
    assert visor._visor_public_source(source)["nombre"] == source["label"]
    assert visor._visor_public_preview({}) is None
    assert visor._visor_public_warning({}) == {
        "nivel": "warning",
        "codigo": "warning",
        "mensaje": "",
    }
    assert visor._visor_public_tile(
        {
            "id": "t1",
            "row": 1,
            "col": 2,
            "filename": "tile.jpg",
            "label": "Tile",
            "bounds": {"south": 1, "west": 2, "north": 3, "east": 4},
            "bbox3857": {"xmin": 1},
            "width": 100,
            "height": 50,
            "download_url": "/download",
        }
    )["limites"] == {"sur": 1, "oeste": 2, "norte": 3, "este": 4}

    with app.test_request_context("/"):
        assert visor._visor_validate_bbox(
            {"south": 3, "west": 4, "north": 1, "east": 2}
        ) == (1.0, 2.0, 3.0, 4.0)
        with pytest.raises(ValueError, match="Coordenadas"):
            visor._visor_validate_bbox(None)
        with pytest.raises(ValueError, match="lado cero"):
            visor._visor_validate_bbox(
                {"sur": 1, "oeste": 2, "norte": 1, "este": 3}
            )


def test_coordinate_wms_and_http_helpers(monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    bbox3857 = visor._visor_bbox_to_mercator((40.0, -4.0, 41.0, -3.0))
    latlng = visor._visor_bbox_to_latlng(bbox3857)
    assert latlng["sur"] == pytest.approx(40.0)
    assert latlng["oeste"] == pytest.approx(-4.0)

    url = visor._visor_build_wms_url(
        "https://example.test/wms", "layer name", bbox3857, 256, 128
    )
    assert "REQUEST=GetMap" in url
    assert "WIDTH=256" in url
    assert "layer+name" in url

    class FakeHeaders:
        def get_content_type(self):
            """Devuelve la cabecera Content-Type simulada."""
            return "image/jpeg"

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            """Entra en el contexto simulado de respuesta HTTP."""
            return self

        def __exit__(self, *args):
            """Sale del contexto simulado de respuesta HTTP."""
            return False

        def read(self):
            """Devuelve bytes simulados de una respuesta HTTP."""
            return b"ok"

    monkeypatch.setattr(
        visor, "urlopen", lambda request, timeout: FakeResponse()
    )
    assert visor._visor_http_get("https://example.test") == (
        200,
        "image/jpeg",
        b"ok",
    )

    class FakeHTTPError(HTTPError):
        def __init__(self):
            """Inicializa el doble de prueba."""
            super().__init__(
                "url", 404, "not found", FakeHeaders(), BytesIO(b"missing")
            )

    monkeypatch.setattr(
        visor,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(FakeHTTPError()),
    )
    assert visor._visor_http_get("https://example.test") == (
        404,
        "image/jpeg",
        b"missing",
    )

    monkeypatch.setattr(
        visor,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("down")),
    )
    with pytest.raises(RuntimeError, match="down"):
        visor._visor_http_get("https://example.test")


def test_blank_image_detection():
    """Verifica el comportamiento esperado en el caso previsto."""
    assert visor._visor_image_is_probably_blank(_png_rgba_bytes(alpha=0))
    assert visor._visor_image_is_probably_blank(_jpeg_bytes())
    assert not visor._visor_image_is_probably_blank(_varied_jpeg_bytes())
    assert not visor._visor_image_is_probably_blank(b"not-image")


def test_probe_resolution_select_and_build_tiles(monkeypatch, app):
    """Verifica el comportamiento esperado en el caso previsto."""
    source_low = {
        "id": "low",
        "label": "Low",
        "year": 2020,
        "native_resolution": 0.5,
        "service_url": "u",
        "layer": "l",
        "service": "WMS",
    }
    source_high = {
        "id": "high",
        "label": "High",
        "year": 2024,
        "native_resolution": 0.1,
        "service_url": "u",
        "layer": "l",
        "service": "WMS",
    }
    monkeypatch.setattr(visor, "VISOR_PNOA_SOURCES", [source_low, source_high])

    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (500, "image/jpeg", b"x"),
    )
    assert not visor._visor_probe_source(source_high, (0, 0, 10, 10))
    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (200, "text/xml", b"<xml/>"),
    )
    assert not visor._visor_probe_source(source_high, (0, 0, 10, 10))
    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (200, "text/plain", b"body"),
    )
    assert not visor._visor_probe_source(source_high, (0, 0, 10, 10))
    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (200, "image/jpeg", b""),
    )
    assert not visor._visor_probe_source(source_high, (0, 0, 10, 10))
    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert not visor._visor_probe_source(source_high, (0, 0, 10, 10))
    monkeypatch.setattr(
        visor,
        "_visor_http_get",
        lambda url, timeout=15: (200, "image/jpeg", _varied_jpeg_bytes()),
    )
    assert visor._visor_probe_source(source_high, (0, 0, 10, 10))

    monkeypatch.setattr(
        visor,
        "_visor_probe_source",
        lambda source, bbox: source["id"] == "low",
    )
    with app.test_request_context("/"):
        source, resolution, warnings = visor._visor_select_source(
            (0, 0, 1200, 800), 0.1
        )
        assert source["id"] == "low"
        assert resolution == 0.5
        assert warnings[0]["code"] == "fallback_resolution"

        tiles, rows, cols = visor._visor_build_tiles(
            (0, 0, 1200, 800), 1.0, 500, 400, source
        )
        assert rows == 2
        assert cols == 3
        assert len(tiles) == 6
        assert tiles[-1]["ancho"] == 200
        assert tiles[-1]["alto"] == 400

    monkeypatch.setattr(
        visor, "_visor_probe_source", lambda source, bbox: False
    )
    source, resolution, warnings = visor._visor_select_source(
        (0, 0, 1, 1), 0.1
    )
    assert source is None
    assert resolution is None


def test_parse_and_fetch_tile_errors(monkeypatch, app):
    """Verifica el comportamiento esperado en el caso previsto."""
    source = visor.VISOR_PNOA_SOURCES[0]
    args = {
        "fuente_id": source["id"],
        "xmin": "0",
        "ymin": "1",
        "xmax": "2",
        "ymax": "3",
        "ancho": "20",
        "alto": "10",
    }
    parsed = visor._visor_parse_tile_request(args)
    assert parsed[0] is source
    assert parsed[2:4] == (20, 10)
    assert parsed[4].endswith(".jpg")

    with app.test_request_context("/"):
        with pytest.raises(ValueError, match="fuente"):
            visor._visor_parse_tile_request({"fuente_id": "missing"})
        with pytest.raises(ValueError, match="parámetros"):
            visor._visor_parse_tile_request(
                {"fuente_id": source["id"], "xmin": "bad"}
            )
        bad_size = dict(args, ancho="0")
        with pytest.raises(ValueError, match="tamaño"):
            visor._visor_parse_tile_request(bad_size)

        monkeypatch.setattr(
            visor,
            "_visor_http_get",
            lambda url, timeout=30: (500, "image/jpeg", b"x"),
        )
        with pytest.raises(RuntimeError, match="descargar"):
            visor._visor_fetch_tile_bytes(source, (0, 0, 1, 1), 10, 10)
        monkeypatch.setattr(
            visor,
            "_visor_http_get",
            lambda url, timeout=30: (200, "text/xml", b"<xml/>"),
        )
        with pytest.raises(RuntimeError, match="error"):
            visor._visor_fetch_tile_bytes(source, (0, 0, 1, 1), 10, 10)
        monkeypatch.setattr(
            visor,
            "_visor_http_get",
            lambda url, timeout=30: (200, "image/jpeg", _jpeg_bytes()),
        )
        with pytest.raises(RuntimeError, match="vacía"):
            visor._visor_fetch_tile_bytes(source, (0, 0, 1, 1), 10, 10)
        monkeypatch.setattr(
            visor,
            "_visor_http_get",
            lambda url, timeout=30: (200, "image/jpeg", _varied_jpeg_bytes()),
        )
        assert visor._visor_fetch_tile_bytes(
            source, (0, 0, 1, 1), 10, 10
        ).startswith(b"\xff\xd8")


def test_grid_plan_error_paths_and_warnings(
    client, app, force_login, monkeypatch
):
    """Verifica la generación de cuadrícula en el caso previsto."""
    force_login()
    payload = {
        "limites": {"sur": 40, "oeste": -4, "norte": 41, "este": -3},
        "resolucion": 0.25,
    }

    assert (
        client.post("/visor/grid-plan", json={"limites": None}).status_code
        == 400
    )
    assert (
        client.post(
            "/visor/grid-plan", json={**payload, "resolucion": 999}
        ).status_code
        == 400
    )

    monkeypatch.setattr(
        visor,
        "_visor_select_source",
        lambda bbox, resolution: (None, None, []),
    )
    assert client.post("/visor/grid-plan", json=payload).status_code == 422

    source = visor.VISOR_PNOA_SOURCES[0]
    monkeypatch.setattr(
        visor,
        "_visor_select_source",
        lambda bbox, resolution: (source, resolution, []),
    )
    monkeypatch.setattr(
        visor,
        "_visor_build_tiles",
        lambda *args: (
            [
                {
                    "id": f"t{i}",
                    "fila": 1,
                    "columna": i,
                    "nombre_archivo": f"t{i}.jpg",
                    "nombre": "t",
                    "limites": {},
                    "limites_3857": {},
                    "ancho": 1,
                    "alto": 1,
                    "url_descarga": "/d",
                }
                for i in range(visor.VISOR_TILE_WARNING_THRESHOLD + 1)
            ],
            1,
            visor.VISOR_TILE_WARNING_THRESHOLD + 1,
        ),
    )
    monkeypatch.setattr(
        visor,
        "save_generated_zone",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    response = client.post("/visor/grid-plan", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["parcela_id"] is None
    assert {warning["codigo"] for warning in data["avisos"]} == {
        "large_grid",
        "collection_save_failed",
    }

    monkeypatch.setattr(
        visor,
        "_visor_select_source",
        lambda bbox, resolution: (_ for _ in ()).throw(
            RuntimeError("wms down")
        ),
    )
    assert client.post("/visor/grid-plan", json=payload).status_code == 502
    monkeypatch.setattr(
        visor,
        "_visor_select_source",
        lambda bbox, resolution: (_ for _ in ()).throw(Exception("boom")),
    )
    assert client.post("/visor/grid-plan", json=payload).status_code == 500


def test_download_tile_and_zip_routes(client, app, force_login, monkeypatch):
    """Verifica las descargas en el caso previsto."""
    force_login()
    source = visor.VISOR_PNOA_SOURCES[0]

    assert (
        client.get("/visor/download/tile?fuente_id=missing").status_code == 400
    )
    monkeypatch.setattr(
        visor,
        "_visor_fetch_tile_bytes",
        lambda *args: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert (
        client.get(
            "/visor/download/tile"
            f"?fuente_id={source['id']}"
            "&xmin=0&ymin=0&xmax=1&ymax=1"
            "&ancho=1&alto=1"
        ).status_code
        == 502
    )

    monkeypatch.setattr(
        visor, "_visor_fetch_tile_bytes", lambda *args: _varied_jpeg_bytes()
    )
    response = client.get(
        "/visor/download/tile"
        f"?fuente_id={source['id']}"
        "&xmin=0&ymin=0&xmax=1&ymax=1"
        "&ancho=1&alto=1&nombre_archivo=a.jpg"
    )
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"

    assert (
        client.post(
            "/visor/download/zip", json={"fuente_id": "missing", "teselas": []}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/visor/download/zip",
            json={"fuente_id": source["id"], "teselas": []},
        ).status_code
        == 400
    )
    too_many = [{"id": str(i)} for i in range(visor.VISOR_ZIP_TILE_LIMIT + 1)]
    assert (
        client.post(
            "/visor/download/zip",
            json={"fuente_id": source["id"], "teselas": too_many},
        ).status_code
        == 400
    )

    tiles = [
        {
            "id": "ok",
            "limites_3857": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1},
            "ancho": 1,
            "alto": 1,
            "nombre_archivo": "ok.jpg",
        },
        {"id": "bad", "limites_3857": {"xmin": "bad"}, "ancho": 1, "alto": 1},
    ]
    response = client.post(
        "/visor/download/zip",
        json={"fuente_id": source["id"], "teselas": tiles},
    )
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.data)) as zf:
        assert "ok.jpg" in zf.namelist()
        log = json.loads(zf.read("log.json"))
    assert log["descargadas"] == ["ok.jpg"]
    assert log["fallidas"][0]["tesela"] == "bad"
