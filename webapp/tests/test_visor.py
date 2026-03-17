"""
Pruebas básicas de la pantalla Visor y sus endpoints auxiliares.

Estas pruebas verifican que la vista del visor responde, que el backend
puede devolver un plan de cuadrícula sin depender del IGN y que la descarga de
una tesela individual funciona mediante el proxy backend.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

from trazasytrazadas import visor as visor_module


def test_visor_page_renders(client):
    """Comprueba que la nueva pantalla del visor se renderiza."""
    response = client.get("/visor")
    assert response.status_code == 200
    assert "Visor".encode("utf-8") in response.data
    assert b"window.VISOR_APP" in response.data


def test_visor_grid_plan_returns_tiles(client, monkeypatch):
    """Verifica que /visor/grid-plan devuelve una cuadrícula planificada."""
    source = visor_module._visor_source_by_id("pnoa2023")

    monkeypatch.setattr(
        visor_module,
        "_visor_select_source",
        lambda _bbox, _resolution: (source, 0.25, []),
    )

    def _fake_tiles(_bbox, _resolution, _tile_size, _source):
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
                    "width": 512,
                    "height": 512,
                    "download_url": "/visor/download/tile?source_id=pnoa2023",
                }
            ],
            1,
            1,
        )

    monkeypatch.setattr(visor_module, "_visor_build_tiles", _fake_tiles)

    response = client.post(
        "/visor/grid-plan",
        json={
            "bbox": {
                "south": 40.0,
                "west": -4.0,
                "north": 40.1,
                "east": -3.9,
            },
            "resolution": 0.25,
            "tile_size": 512,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source"]["id"] == "pnoa2023"
    assert payload["tile_count"] == 1
    assert payload["tiles"][0]["filename"] == "tile_1.jpg"


def test_visor_download_tile_uses_backend_proxy(client, monkeypatch):
    """Comprueba que la descarga individual devuelve una imagen JPEG."""
    monkeypatch.setattr(
        visor_module,
        "_visor_fetch_tile_bytes",
        lambda _source, _bbox, _width, _height: b"fake-image-bytes",
    )

    response = client.get(
        "/visor/download/tile",
        query_string={
            "source_id": "pnoa2023",
            "xmin": 0,
            "ymin": 0,
            "xmax": 1,
            "ymax": 1,
            "width": 256,
            "height": 256,
            "filename": "tile.jpg",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"fake-image-bytes"
