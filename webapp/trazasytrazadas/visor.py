"""
Rutas y utilidades del visor cartográfico PNOA.

Este módulo encapsula la lógica del visor: selección automática de fuentes
PNOA con fallback por resolución, generación de cuadrículas, descarga de
teselas individuales y empaquetado de descargas en ZIP.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io
import json
import math
import zipfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from flask import (
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_babel import gettext as _

# Configuración del visor PNOA.
VISOR_RESOLUTION_STEPS = [0.1, 0.25, 0.5, 1.0, 2.0]
VISOR_DEFAULT_TILE_WIDTH = 1024
VISOR_DEFAULT_TILE_HEIGHT = 640
VISOR_TILE_WARNING_THRESHOLD = 64
VISOR_ZIP_TILE_LIMIT = 256
VISOR_WMS_PNOA_HISTORY = "https://www.ign.es/wms/pnoa-historico"
VISOR_WMS_PNOA_LATEST = "https://www.ign.es/wms-inspire/pnoa-ma"

VISOR_PNOA_SOURCES = [
    {
        "id": "ma_latest",
        "label": "PNOA Máxima Actualidad",
        "service_url": VISOR_WMS_PNOA_LATEST,
        "layer": "OI.OrthoimageCoverage",
        "native_resolution": 0.15,
        "year": 9999,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_LATEST,
            "layer": "OI.OrthoimageCoverage",
        },
    },
    {
        "id": "pnoa2023",
        "label": "PNOA 2023",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2023",
        "native_resolution": 0.15,
        "year": 2023,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2023",
        },
    },
    {
        "id": "pnoa2022",
        "label": "PNOA 2022",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2022",
        "native_resolution": 0.25,
        "year": 2022,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2022",
        },
    },
    {
        "id": "pnoa2021",
        "label": "PNOA 2021",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2021",
        "native_resolution": 0.15,
        "year": 2021,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2021",
        },
    },
    {
        "id": "pnoa2020",
        "label": "PNOA 2020",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2020",
        "native_resolution": 0.15,
        "year": 2020,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2020",
        },
    },
    {
        "id": "pnoa2019",
        "label": "PNOA 2019",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2019",
        "native_resolution": 0.25,
        "year": 2019,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2019",
        },
    },
    {
        "id": "pnoa10_2018",
        "label": "PNOA 10 Galicia 2018",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2018",
        "native_resolution": 0.1,
        "year": 2018,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2018",
        },
    },
    {
        "id": "pnoa2018",
        "label": "PNOA 2018",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2018",
        "native_resolution": 0.15,
        "year": 2018,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2018",
        },
    },
    {
        "id": "pnoa2017",
        "label": "PNOA 2017",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2017",
        "native_resolution": 0.25,
        "year": 2017,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2017",
        },
    },
    {
        "id": "pnoa10_2016",
        "label": "PNOA 10 Madrid 2016",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2016",
        "native_resolution": 0.1,
        "year": 2016,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2016",
        },
    },
    {
        "id": "pnoa2016",
        "label": "PNOA 2016",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2016",
        "native_resolution": 0.25,
        "year": 2016,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2016",
        },
    },
    {
        "id": "pnoa2015",
        "label": "PNOA 2015",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2015",
        "native_resolution": 0.25,
        "year": 2015,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2015",
        },
    },
    {
        "id": "pnoa2014",
        "label": "PNOA 2014",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2014",
        "native_resolution": 0.1,
        "year": 2014,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2014",
        },
    },
    {
        "id": "pnoa10_2013",
        "label": "PNOA 10 Madrid 2013",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2013",
        "native_resolution": 0.1,
        "year": 2013,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2013",
        },
    },
    {
        "id": "pnoa2013",
        "label": "PNOA 2013",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2013",
        "native_resolution": 0.5,
        "year": 2013,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2013",
        },
    },
    {
        "id": "pnoa2012",
        "label": "PNOA 2012",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2012",
        "native_resolution": 0.25,
        "year": 2012,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2012",
        },
    },
    {
        "id": "pnoa2011",
        "label": "PNOA 2011",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2011",
        "native_resolution": 0.25,
        "year": 2011,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2011",
        },
    },
    {
        "id": "pnoa2010",
        "label": "PNOA 2010",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2010",
        "native_resolution": 0.25,
        "year": 2010,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2010",
        },
    },
    {
        "id": "pnoa10_2009",
        "label": "PNOA 10 Madrid 2009",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2009",
        "native_resolution": 0.1,
        "year": 2009,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2009",
        },
    },
    {
        "id": "pnoa2009",
        "label": "PNOA 2009",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2009",
        "native_resolution": 0.25,
        "year": 2009,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2009",
        },
    },
    {
        "id": "pnoa10_2008",
        "label": "PNOA 10 Illes Balears 2008",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2008",
        "native_resolution": 0.1,
        "year": 2008,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2008",
        },
    },
    {
        "id": "pnoa2008",
        "label": "PNOA 2008",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2008",
        "native_resolution": 0.25,
        "year": 2008,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2008",
        },
    },
    {
        "id": "pnoa10_2007",
        "label": "PNOA 10 Castilla-La Mancha 2007",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "pnoa10_2007",
        "native_resolution": 0.1,
        "year": 2007,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "pnoa10_2007",
        },
    },
    {
        "id": "pnoa2007",
        "label": "PNOA 2007",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2007",
        "native_resolution": 0.25,
        "year": 2007,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2007",
        },
    },
    {
        "id": "pnoa2006",
        "label": "PNOA 2006",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2006",
        "native_resolution": 0.25,
        "year": 2006,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2006",
        },
    },
    {
        "id": "pnoa2005",
        "label": "PNOA 2005",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2005",
        "native_resolution": 0.25,
        "year": 2005,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2005",
        },
    },
    {
        "id": "pnoa2004",
        "label": "PNOA 2004",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "PNOA2004",
        "native_resolution": 0.25,
        "year": 2004,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "PNOA2004",
        },
    },
    {
        "id": "sigpac",
        "label": "SIGPAC (1997-2003)",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "SIGPAC",
        "native_resolution": 1.0,
        "year": 2003,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "SIGPAC",
        },
    },
    {
        "id": "olistat",
        "label": "OLISTAT (1997-1998)",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "OLISTAT",
        "native_resolution": 1.0,
        "year": 1998,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "OLISTAT",
        },
    },
    {
        "id": "nacional_1981_1986",
        "label": "Nacional (1981-1986)",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "Nacional_1981-1986",
        "native_resolution": 0.5,
        "year": 1986,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "Nacional_1981-1986",
        },
    },
    {
        "id": "interministerial_1973_1986",
        "label": "Interministerial (1973-1986)",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "Interministerial_1973-1986",
        "native_resolution": 0.5,
        "year": 1986,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "Interministerial_1973-1986",
        },
    },
    {
        "id": "ams_1956_1957",
        "label": "Americano serie B (1956-1957)",
        "service_url": VISOR_WMS_PNOA_HISTORY,
        "layer": "AMS_1956-1957",
        "native_resolution": 0.5,
        "year": 1957,
        "service": "WMS",
        "preview": {
            "type": "wms",
            "url": VISOR_WMS_PNOA_HISTORY,
            "layer": "AMS_1956-1957",
        },
    },
]


def _visor_source_by_id(source_id: str) -> dict | None:
    """Devuelve la definición de una fuente del visor por su identificador."""
    for source in VISOR_PNOA_SOURCES:
        if source["id"] == source_id:
            return source
    return None


def _visor_validate_bbox(
    payload_bbox: dict,
) -> tuple[float, float, float, float]:
    """Valida y normaliza un bounding box geográfico en EPSG:4326."""
    try:
        south = float(payload_bbox["south"])
        west = float(payload_bbox["west"])
        north = float(payload_bbox["north"])
        east = float(payload_bbox["east"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(_("Coordenadas del rectángulo no válidas.")) from exc

    if south == north or west == east:
        raise ValueError(
            _("El rectángulo seleccionado no puede tener lado cero.")
        )

    return (
        min(south, north),
        min(west, east),
        max(south, north),
        max(west, east),
    )


def _lon_to_mercator_x(lon: float) -> float:
    """Convierte longitud geográfica a coordenada X en EPSG:3857."""
    radius = 6378137.0
    return radius * math.radians(lon)


def _lat_to_mercator_y(lat: float) -> float:
    """Convierte latitud geográfica a coordenada Y en EPSG:3857."""
    radius = 6378137.0
    clipped = max(min(lat, 85.05112878), -85.05112878)
    return radius * math.log(math.tan(math.pi / 4 + math.radians(clipped) / 2))


def _mercator_x_to_lon(x: float) -> float:
    """Convierte coordenada X en EPSG:3857 a longitud geográfica."""
    radius = 6378137.0
    return math.degrees(x / radius)


def _mercator_y_to_lat(y: float) -> float:
    """Convierte coordenada Y en EPSG:3857 a latitud geográfica."""
    radius = 6378137.0
    return math.degrees(2 * math.atan(math.exp(y / radius)) - math.pi / 2)


def _visor_bbox_to_mercator(
    bbox4326: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Convierte un bbox geográfico a EPSG:3857."""
    south, west, north, east = bbox4326
    xmin = _lon_to_mercator_x(west)
    xmax = _lon_to_mercator_x(east)
    ymin = _lat_to_mercator_y(south)
    ymax = _lat_to_mercator_y(north)
    return xmin, ymin, xmax, ymax


def _visor_bbox_to_latlng(
    bbox3857: tuple[float, float, float, float],
) -> dict[str, float]:
    """Convierte un bbox en EPSG:3857 a coordenadas geográficas."""
    xmin, ymin, xmax, ymax = bbox3857
    return {
        "south": _mercator_y_to_lat(ymin),
        "west": _mercator_x_to_lon(xmin),
        "north": _mercator_y_to_lat(ymax),
        "east": _mercator_x_to_lon(xmax),
    }


def _visor_build_wms_url(
    service_url: str,
    layer: str,
    bbox3857: tuple[float, float, float, float],
    width: int,
    height: int,
) -> str:
    """Construye una petición GetMap WMS en EPSG:3857."""
    xmin, ymin, xmax, ymax = bbox3857
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "FORMAT": "image/jpeg",
        "TRANSPARENT": "FALSE",
        "SRS": "EPSG:3857",
        "BBOX": f"{xmin},{ymin},{xmax},{ymax}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
    }
    return f"{service_url}?{urlencode(params)}"


def _visor_http_get(url: str, timeout: int = 20) -> tuple[int, str, bytes]:
    """Realiza una petición HTTP y devuelve código,
        tipo de contenido y bytes."""
    request_obj = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request_obj, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            return response.status, content_type, response.read()
    except HTTPError as exc:
        content_type = exc.headers.get_content_type() if exc.headers else ""
        return exc.code, content_type, exc.read()
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def _visor_image_is_probably_blank(image_bytes: bytes) -> bool:
    """
    Detecta imágenes vacías o sin datos útiles de manera conservadora.

    Se consideran vacías respuestas transparentes, con un único color o con una
    varianza prácticamente nula en una miniatura reducida.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.mode in {"RGBA", "LA"}:
                alpha = image.getchannel("A")
                alpha_min, alpha_max = alpha.getextrema()
                if alpha_max == 0:
                    return True

            rgb = image.convert("RGB")
            thumb = rgb.resize((24, 24))
            colors = thumb.getcolors(maxcolors=64)
            if colors is not None and len(colors) <= 2:
                return True

            arr = np.asarray(thumb, dtype=np.float32)
            return float(arr.var()) < 1.0
    except Exception:
        return False


def _visor_probe_source(
    source: dict,
    bbox3857: tuple[float, float, float, float],
) -> bool:
    """Comprueba si una fuente WMS devuelve imagen válida sobre un bbox."""
    probe_url = _visor_build_wms_url(
        source["service_url"],
        source["layer"],
        bbox3857,
        width=96,
        height=96,
    )
    status_code, content_type, body = _visor_http_get(probe_url, timeout=15)

    if status_code >= 400:
        return False
    if not body:
        return False
    if "xml" in content_type or body.lstrip().startswith(b"<"):
        return False
    if not content_type.startswith("image/"):
        return False
    if _visor_image_is_probably_blank(body):
        return False

    return True


def _visor_resolution_levels(requested_resolution: float) -> list[float]:
    """Devuelve la secuencia de resoluciones a probar desde la solicitada."""
    return [
        level
        for level in VISOR_RESOLUTION_STEPS
        if level >= requested_resolution - 1e-9
    ]


def _visor_select_source(
    bbox3857: tuple[float, float, float, float],
    requested_resolution: float,
) -> tuple[dict | None, float | None, list[dict]]:
    """
    Selecciona la mejor ortofoto disponible para el bbox y la resolución.

    La lógica es:
    1. Probar la resolución pedida.
    2. Si no hay fuente que la satisfaga, degradar a la siguiente resolución.
    3. Dentro de cada resolución, escoger la cobertura más reciente.
    """
    warnings: list[dict] = []

    for actual_resolution in _visor_resolution_levels(requested_resolution):
        candidates = [
            source
            for source in VISOR_PNOA_SOURCES
            if source["native_resolution"] <= actual_resolution + 1e-9
        ]
        candidates.sort(
            key=lambda item: (
                -item["year"],
                item["native_resolution"],
                item["label"],
            )
        )

        for source in candidates:
            if _visor_probe_source(source, bbox3857):
                if actual_resolution > requested_resolution:
                    warnings.append(
                        {
                            "level": "warning",
                            "code": "fallback_resolution",
                            "message": _(
                                "La resolución solicitada no está disponible "
                                "en la zona. Se ha aplicado fallback a "
                                "%(resolution)s m/px.",
                                resolution=f"{actual_resolution:.2f}",
                            ),
                        }
                    )
                return source, actual_resolution, warnings

    return None, None, warnings


def _visor_build_tiles(
    bbox3857: tuple[float, float, float, float],
    actual_resolution: float,
    tile_width: int,
    tile_height: int,
    source: dict,
) -> tuple[list[dict], int, int]:
    """Genera la cuadrícula de teselas descargables para un bbox."""
    xmin, ymin, xmax, ymax = bbox3857
    tile_span_x_m = actual_resolution * tile_width
    tile_span_y_m = actual_resolution * tile_height
    width_m = xmax - xmin
    height_m = ymax - ymin
    cols = max(1, math.ceil(width_m / tile_span_x_m))
    rows = max(1, math.ceil(height_m / tile_span_y_m))

    tiles: list[dict] = []
    for row in range(rows):
        tile_ymax = ymax - row * tile_span_y_m
        tile_ymin = max(ymin, tile_ymax - tile_span_y_m)

        for col in range(cols):
            tile_xmin = xmin + col * tile_span_x_m
            tile_xmax = min(xmax, tile_xmin + tile_span_x_m)

            tile_width_px = max(
                1,
                min(
                    tile_width,
                    math.ceil((tile_xmax - tile_xmin) / actual_resolution),
                ),
            )
            tile_height_px = max(
                1,
                min(
                    tile_height,
                    math.ceil((tile_ymax - tile_ymin) / actual_resolution),
                ),
            )

            bbox_tile = (tile_xmin, tile_ymin, tile_xmax, tile_ymax)
            tile_id = f"r{row + 1:02d}_c{col + 1:02d}"
            filename = (
                f"{source['id']}_{tile_id}_{actual_resolution:.2f}mpp.jpg"
            )

            tiles.append(
                {
                    "id": tile_id,
                    "row": row + 1,
                    "col": col + 1,
                    "filename": filename,
                    "label": _(
                        "Tesela %(row)s-%(col)s",
                        row=row + 1,
                        col=col + 1,
                    ),
                    "bounds": _visor_bbox_to_latlng(bbox_tile),
                    "bbox3857": {
                        "xmin": tile_xmin,
                        "ymin": tile_ymin,
                        "xmax": tile_xmax,
                        "ymax": tile_ymax,
                    },
                    "width": tile_width_px,
                    "height": tile_height_px,
                    "download_url": url_for(
                        "trazas.visor_download_tile",
                        source_id=source["id"],
                        xmin=tile_xmin,
                        ymin=tile_ymin,
                        xmax=tile_xmax,
                        ymax=tile_ymax,
                        width=tile_width_px,
                        height=tile_height_px,
                        filename=filename,
                    ),
                }
            )

    return tiles, rows, cols


def _visor_parse_tile_request(
    args: dict,
) -> tuple[dict, tuple[float, ...], int, int, str]:
    """Valida la petición de descarga de una tesela individual."""
    source_id = args.get("source_id", "")
    source = _visor_source_by_id(source_id)
    if source is None:
        raise ValueError(_("La fuente solicitada no existe."))

    try:
        xmin = float(args["xmin"])
        ymin = float(args["ymin"])
        xmax = float(args["xmax"])
        ymax = float(args["ymax"])
        width = int(args["width"])
        height = int(args["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            _("Los parámetros de descarga no son válidos.")) from exc

    if width <= 0 or height <= 0:
        raise ValueError(_("El tamaño de descarga no es válido."))

    filename = args.get("filename") or f"{source_id}.jpg"
    return source, (xmin, ymin, xmax, ymax), width, height, filename


def _visor_fetch_tile_bytes(
    source: dict,
    bbox3857: tuple[float, float, float, float],
    width: int,
    height: int,
) -> bytes:
    """Descarga una tesela desde el servicio WMS del IGN."""
    tile_url = _visor_build_wms_url(
        source["service_url"],
        source["layer"],
        bbox3857,
        width,
        height,
    )
    status_code, content_type, body = _visor_http_get(tile_url, timeout=30)

    if status_code >= 400 or not body:
        raise RuntimeError(_("No se ha podido descargar la imagen remota."))
    if "xml" in content_type or body.lstrip().startswith(b"<"):
        raise RuntimeError(_("El servicio remoto ha respondido con un error."))
    if _visor_image_is_probably_blank(body):
        raise RuntimeError(
            _("La ortofoto devuelta está vacía para esta tesela."))

    return body


def register_visor_routes(bp) -> None:
    """
    Registra en el blueprint principal las rutas del visor cartográfico.
    """

    @bp.route("/visor", methods=["GET"])
    def visor():
        """Renderiza la pantalla del visor cartográfico."""
        return render_template("visor.html")

    @bp.route("/visor/grid-plan", methods=["POST"])
    def visor_grid_plan():
        """Devuelve la planificación de teselas para el visor cartográfico."""
        payload = request.get_json(silent=True) or {}

        try:
            bbox4326 = _visor_validate_bbox(payload.get("bbox", {}))
            requested_resolution = float(payload.get("resolution", 0.25))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if requested_resolution not in VISOR_RESOLUTION_STEPS:
            return (
                jsonify(
                    {
                        "error": _(
                            "La resolución solicitada no está soportada."
                        )
                    }
                ),
                400,
            )

        tile_width = VISOR_DEFAULT_TILE_WIDTH
        tile_height = VISOR_DEFAULT_TILE_HEIGHT

        try:
            bbox3857 = _visor_bbox_to_mercator(bbox4326)
            source, actual_resolution, warnings = _visor_select_source(
                bbox3857,
                requested_resolution,
            )

            if source is None or actual_resolution is None:
                return (
                    jsonify(
                        {
                            "error": _(
                                "No se ha encontrado cobertura PNOA adecuada"
                                " para el área seleccionada."
                            )
                        }
                    ),
                    422,
                )

            tiles, rows, cols = _visor_build_tiles(
                bbox3857,
                actual_resolution,
                tile_width,
                tile_height,
                source,
            )

            if len(tiles) > VISOR_TILE_WARNING_THRESHOLD:
                warnings.append(
                    {
                        "level": "warning",
                        "code": "large_grid",
                        "message": _(
                            "La cuadrícula contiene %(count)s teselas y puede "
                            "generar una descarga pesada.",
                            count=len(tiles),
                        ),
                    }
                )

            return jsonify(
                {
                    "source": {
                        "id": source["id"],
                        "label": source["label"],
                        "service": source["service"],
                        "layer": source["layer"],
                    },
                    "preview": source.get("preview"),
                    "requested_resolution": requested_resolution,
                    "actual_resolution": actual_resolution,
                    "tile_width": tile_width,
                    "tile_height": tile_height,
                    "tile_count": len(tiles),
                    "rows": rows,
                    "cols": cols,
                    "warnings": warnings,
                    "tiles": tiles,
                }
            )

        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception:
            current_app.logger.exception(
                "Error generando la cuadrícula del visor"
            )
            return (
                jsonify(
                    {
                        "error": _(
                            "Se ha producido un error interno al generar la "
                            "cuadrícula."
                        )
                    }
                ),
                500,
            )

    @bp.route("/visor/download/tile", methods=["GET"])
    def visor_download_tile():
        """Descarga una tesela individual del visor mediante proxy backend."""
        try:
            source, bbox3857, width, height, filename = (
                _visor_parse_tile_request(request.args)
            )
            image_bytes = _visor_fetch_tile_bytes(
                source,
                bbox3857,
                width,
                height,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name=filename,
        )

    @bp.route("/visor/download/zip", methods=["POST"])
    def visor_download_zip():
        """Genera un ZIP con las teselas del visor
            usando el backend como proxy."""
        payload = request.get_json(silent=True) or {}
        source_id = payload.get("source_id", "")
        source = _visor_source_by_id(source_id)
        tiles = payload.get("tiles", [])

        if source is None:
            return jsonify(
                {"error": _("La fuente solicitada no existe.")}
            ), 400

        if not isinstance(tiles, list) or not tiles:
            return (
                jsonify(
                    {
                        "error": _(
                            "No se han recibido teselas para descargar."
                        )
                    }
                ),
                400,
            )

        if len(tiles) > VISOR_ZIP_TILE_LIMIT:
            return (
                jsonify(
                    {
                        "error": _(
                            "El ZIP supera el límite permitido de "
                            "%(limit)s teselas.",
                            limit=VISOR_ZIP_TILE_LIMIT,
                        )
                    }
                ),
                400,
            )

        zip_buffer = io.BytesIO()
        manifest: dict[str, list] = {"downloaded": [], "failed": []}

        with zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for tile in tiles:
                try:
                    bbox = tile.get("bbox3857", {})
                    bbox3857 = (
                        float(bbox["xmin"]),
                        float(bbox["ymin"]),
                        float(bbox["xmax"]),
                        float(bbox["ymax"]),
                    )
                    width = int(tile.get("width", 0))
                    height = int(tile.get("height", 0))
                    filename = (
                        tile.get("filename")
                        or f"{tile.get('id', 'tile')}.jpg"
                    )
                    image_bytes = _visor_fetch_tile_bytes(
                        source,
                        bbox3857,
                        width,
                        height,
                    )
                    zf.writestr(filename, image_bytes)
                    manifest["downloaded"].append(filename)
                except Exception as exc:  # pragma: no cover
                    manifest["failed"].append(
                        {
                            "tile": tile.get("id", "unknown"),
                            "error": str(exc),
                        }
                    )

            zf.writestr(
                "manifest.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )

        zip_buffer.seek(0)
        zip_name = f"visor_{source_id}_tiles.zip"
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )
