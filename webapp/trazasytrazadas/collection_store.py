"""
===============================================================================
Acceso a datos para la colección de imágenes basada en SQLite.

Este módulo encapsula la persistencia de parcelas y fotos para que
las rutas de Flask y el visor reutilicen una única capa de acceso a datos.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
from math import ceil
from urllib.parse import urlparse

from flask import url_for
from flask_babel import gettext as _

from .db import get_db

DEFAULT_SYSTEM_USER_ID = 1
ALLOWED_ZONE_STATUSES = {"pending", "processing", "completed", "failed"}


def _row_to_dict(row) -> dict:
    """Convierte una fila sqlite3.Row en un diccionario estándar."""
    return dict(row) if row is not None else {}


def _json_loads(value, default):
    """Deserializa un JSON persistido devolviendo un valor por defecto."""
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _center_from_bounds(bounds: dict) -> tuple[float, float]:
    """Calcula el centro geográfico aproximado de una tesela."""
    lat = (float(bounds["south"]) + float(bounds["north"])) / 2
    lng = (float(bounds["west"]) + float(bounds["east"])) / 2
    return lat, lng


def _route_path_only(url: str) -> str:
    """Normaliza una URL interna a ruta relativa para almacenamiento."""
    parsed = urlparse(url)
    path = parsed.path or url
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path

def _photo_trace_status(photo: dict) -> str:
    """
    Deriva el estado visual de trazas para una foto.

    Se deja preparado el valor processing para una futura integración
    de cálculo en segundo plano sin rehacer la galería.
    """
    if int(photo.get("trazas", 0)) == 1:
        return "completed"
    return "pending"


def get_default_user_id() -> int:
    """Devuelve el usuario por defecto mientras no exista login."""
    return DEFAULT_SYSTEM_USER_ID


def save_generated_zone(
    *,
    bbox4326: tuple[float, float, float, float],
    origin_point: dict[str, float],
    destination_point: dict[str, float],
    bbox3857: tuple[float, float, float, float],
    requested_resolution: float,
    actual_resolution: float,
    tile_width: int,
    tile_height: int,
    source: dict,
    tiles: list[dict],
    status: str = "pending",
) -> int:
    """
    Persiste una nueva zona generada por el visor y todas sus teselas.

    Cada generación de cuadrícula crea una parcela y tantas fotos como teselas
    existan en el plan devuelto por el visor.
    """
    if status not in ALLOWED_ZONE_STATUSES:
        raise ValueError("Estado de zona no soportado.")

    south, west, north, east = bbox4326
    xmin, ymin, xmax, ymax = bbox3857
    width_m = max(0.0, xmax - xmin)
    height_m = max(0.0, ymax - ymin)
    area_m2 = width_m * height_m

    database = get_db()
    cursor = database.cursor()

    cursor.execute(
        """
        INSERT INTO parcela (
            usuario_id,
            tamano_metros,
            pto_origen_lat,
            pto_origen_lng,
            pto_fin_lat,
            pto_fin_lng,
            bbox_json,
            source_id,
            source_label,
            requested_resolution,
            actual_resolution,
            tile_width,
            tile_height,
            estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            get_default_user_id(),
            area_m2,
            float(origin_point["lat"]),
            float(origin_point["lng"]),
            float(destination_point["lat"]),
            float(destination_point["lng"]),
            json.dumps(
                {
                    "south": south,
                    "west": west,
                    "north": north,
                    "east": east,
                },
                ensure_ascii=False,
            ),
            source["id"],
            source["label"],
            float(requested_resolution),
            float(actual_resolution),
            int(tile_width),
            int(tile_height),
            status,
        ),
    )
    parcel_id = int(cursor.lastrowid)

    for tile in tiles:
        bounds = tile.get("bounds", {})
        bbox_tile = tile.get("bbox3857", {})
        center_lat, center_lng = _center_from_bounds(bounds)
        cursor.execute(
            """
            INSERT INTO foto (
                parcela_id,
                fecha_foto,
                resolucion_valor,
                resolucion_unidad,
                longitud,
                latitud,
                ruta_foto,
                ruta_trazas,
                trazas,
                tile_id,
                row_index,
                col_index,
                filename,
                width,
                height,
                bbox3857_json,
                bounds_json,
                source_id
            ) VALUES (?, DATE('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parcel_id,
                float(actual_resolution),
                "m/px",
                center_lng,
                center_lat,
                _route_path_only(tile.get("download_url", "")),
                None,
                0,
                tile["id"],
                int(tile["row"]),
                int(tile["col"]),
                tile["filename"],
                int(tile["width"]),
                int(tile["height"]),
                json.dumps(bbox_tile, ensure_ascii=False),
                json.dumps(bounds, ensure_ascii=False),
                source["id"],
            ),
        )

    database.commit()
    return parcel_id


def list_zones(*, page: int = 1, per_page: int = 10, search: str = "") -> dict:
    """Devuelve un listado paginado de parcelas de la colección."""
    database = get_db()
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    offset = (page - 1) * per_page
    search = (search or "").strip()
    like = f"%{search}%"

    where_clause = """
        WHERE (
            ? = ''
            OR p.source_label LIKE ?
            OR p.fecha LIKE ?
            OR CAST(p.pto_origen_lat AS TEXT) LIKE ?
            OR CAST(p.pto_origen_lng AS TEXT) LIKE ?
            OR CAST(p.pto_fin_lat AS TEXT) LIKE ?
            OR CAST(p.pto_fin_lng AS TEXT) LIKE ?
        )
    """
    params = (search, like, like, like, like, like, like)

    total = database.execute(
        f"SELECT COUNT(*) AS total FROM parcela p {where_clause}",
        params,
    ).fetchone()["total"]

    rows = database.execute(
        f"""
        SELECT
            p.parcela_id,
            p.pto_origen_lat,
            p.pto_origen_lng,
            p.pto_fin_lat,
            p.pto_fin_lng,
            p.fecha,
            p.estado,
            p.source_label,
            p.source_id,
            p.actual_resolution,
            p.requested_resolution,
            p.tile_width,
            p.tile_height,
            p.created_at,
            COUNT(f.foto_id) AS tile_count,
            MIN(f.foto_id) AS preview_foto_id
        FROM parcela p
        LEFT JOIN foto f ON f.parcela_id = p.parcela_id
        {where_clause}
        GROUP BY p.parcela_id
        ORDER BY p.parcela_id DESC
        LIMIT ? OFFSET ?
        """,
        params + (per_page, offset),
    ).fetchall()

    zones = []
    for row in rows:
        item = _row_to_dict(row)
        item["origin"] = {
            "lat": float(item["pto_origen_lat"]),
            "lng": float(item["pto_origen_lng"]),
        }
        item["destination"] = {
            "lat": float(item["pto_fin_lat"]),
            "lng": float(item["pto_fin_lng"]),
        }
        zones.append(item)

    total_pages = max(1, ceil(total / per_page)) if total else 1
    return {
        "zones": zones,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "search": search,
    }


def get_zone_detail(parcel_id: int) -> dict | None:
    """Recupera una parcela y todas sus fotos asociadas."""
    database = get_db()

    parcel_row = database.execute(
        """
        SELECT
            parcela_id,
            usuario_id,
            tamano_metros,
            pto_origen_lat,
            pto_origen_lng,
            pto_fin_lat,
            pto_fin_lng,
            fecha,
            bbox_json,
            source_id,
            source_label,
            requested_resolution,
            actual_resolution,
            tile_width,
            tile_height,
            estado,
            created_at,
            updated_at
        FROM parcela
        WHERE parcela_id = ?
        """,
        (parcel_id,),
    ).fetchone()

    if parcel_row is None:
        return None

    parcel = _row_to_dict(parcel_row)
    parcel["bbox"] = _json_loads(parcel.pop("bbox_json", "{}"), {})
    parcel["origin"] = {
        "lat": float(parcel["pto_origen_lat"]),
        "lng": float(parcel["pto_origen_lng"]),
    }
    parcel["destination"] = {
        "lat": float(parcel["pto_fin_lat"]),
        "lng": float(parcel["pto_fin_lng"]),
    }

    photo_rows = database.execute(
        """
        SELECT
            foto_id,
            parcela_id,
            fecha_foto,
            resolucion_valor,
            resolucion_unidad,
            longitud,
            latitud,
            ruta_foto,
            ruta_trazas,
            trazas,
            tile_id,
            row_index,
            col_index,
            filename,
            width,
            height,
            bbox3857_json,
            bounds_json,
            source_id,
            created_at
        FROM foto
        WHERE parcela_id = ?
        ORDER BY row_index ASC, col_index ASC, foto_id ASC
        """,
        (parcel_id,),
    ).fetchall()

    photos = []
    for row in photo_rows:
        photo = _row_to_dict(row)
        photo["bbox3857"] = _json_loads(photo.pop("bbox3857_json", "{}"), {})
        photo["bounds"] = _json_loads(photo.pop("bounds_json", "{}"), {})
        photo["trace_status"] = _photo_trace_status(photo)
        photos.append(photo)

    parcel["tile_count"] = len(photos)
    parcel["preview_photo_id"] = photos[0]["foto_id"] if photos else None
    parcel["photos"] = photos
    parcel["completed_tiles"] = sum(
        1 for photo in photos if int(photo["trazas"]) == 1
    )
    return parcel


def get_zone_plan(parcel_id: int) -> dict | None:
    """Reconstruye un plan de visor a partir de una parcela persistida."""
    detail = get_zone_detail(parcel_id)
    if detail is None:
        return None

    from .visor import _visor_source_by_id

    source = _visor_source_by_id(detail["source_id"])
    preview = source.get("preview") if source else None
    rows = max((photo["row_index"] for photo in detail["photos"]), default=0)
    cols = max((photo["col_index"] for photo in detail["photos"]), default=0)

    tiles = []
    for photo in detail["photos"]:
        tiles.append(
            {
                "id": photo["tile_id"],
                "row": photo["row_index"],
                "col": photo["col_index"],
                "filename": photo["filename"],
                "label": _(
                    "Tesela %(row)s-%(col)s",
                    row=photo["row_index"],
                    col=photo["col_index"],
                ),
                "bounds": photo["bounds"],
                "bbox3857": photo["bbox3857"],
                "width": photo["width"],
                "height": photo["height"],
                "download_url": url_for(
                    "trazas.collection_photo_download",
                    photo_id=photo["foto_id"],
                ),
            }
        )

    return {
        "parcel_id": detail["parcela_id"],
        "origin": detail["origin"],
        "destination": detail["destination"],
        "bbox": detail["bbox"],
        "plan": {
            "source": {
                "id": detail["source_id"],
                "label": detail["source_label"],
                "service": source["service"] if source else "WMS",
                "layer": source["layer"] if source else "",
            },
            "preview": preview,
            "requested_resolution": float(detail["requested_resolution"]),
            "actual_resolution": float(detail["actual_resolution"]),
            "tile_width": int(detail["tile_width"]),
            "tile_height": int(detail["tile_height"]),
            "tile_count": len(tiles),
            "rows": rows,
            "cols": cols,
            "warnings": [],
            "tiles": tiles,
        },
    }


def get_photo(photo_id: int) -> dict | None:
    """Recupera una foto concreta de la colección."""
    database = get_db()
    row = database.execute(
        """
        SELECT
            foto_id,
            parcela_id,
            fecha_foto,
            resolucion_valor,
            resolucion_unidad,
            longitud,
            latitud,
            ruta_foto,
            ruta_trazas,
            trazas,
            tile_id,
            row_index,
            col_index,
            filename,
            width,
            height,
            bbox3857_json,
            bounds_json,
            source_id,
            created_at
        FROM foto
        WHERE foto_id = ?
        """,
        (photo_id,),
    ).fetchone()

    if row is None:
        return None

    photo = _row_to_dict(row)
    photo["bbox3857"] = _json_loads(photo.pop("bbox3857_json", "{}"), {})
    photo["bounds"] = _json_loads(photo.pop("bounds_json", "{}"), {})
    return photo


def delete_zone(parcel_id: int) -> bool:
    """Elimina una parcela y sus fotos asociadas mediante borrado en cascada."""
    database = get_db()
    cursor = database.execute(
        "DELETE FROM parcela WHERE parcela_id = ?",
        (parcel_id,),
    )
    database.commit()
    return cursor.rowcount > 0