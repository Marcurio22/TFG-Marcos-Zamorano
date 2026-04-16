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
import os
from math import ceil
import shutil
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import current_app, url_for
from flask_babel import gettext as _

from .db import get_db

DEFAULT_SYSTEM_USER_ID = 1
ALLOWED_ZONE_STATUSES = {"pending", "processing", "completed", "failed"}
COLLECTION_NAME_MAX_LENGTH = 120


class ZoneDeleteError(RuntimeError):
    """Error controlado al eliminar una zona de la colección."""


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


def _ensure_parcela_name_column() -> None:
    """Añade la columna de nombre de colección si aún no existe."""
    database = get_db()
    columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(parcela)").fetchall()
    }
    if "nombre_coleccion" not in columns:
        database.execute(
            "ALTER TABLE parcela ADD COLUMN nombre_coleccion TEXT")
        database.commit()


def _zone_default_name(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> str:
    """Construye el nombre por defecto visible de una colección."""
    return (
        f"{origin_lat:.6f}, {origin_lng:.6f}"
        f" · "
        f"{destination_lat:.6f}, {destination_lng:.6f}"
    )


def _zone_display_name_from_row(row: dict) -> str:
    """Devuelve el nombre visible de la colección a partir de una fila."""
    explicit_name = (row.get("nombre_coleccion") or "").strip()
    if explicit_name:
        return explicit_name

    return _zone_default_name(
        float(row["pto_origen_lat"]),
        float(row["pto_origen_lng"]),
        float(row["pto_fin_lat"]),
        float(row["pto_fin_lng"]),
    )


def photo_retry_is_enabled(photo: dict) -> bool:
    """Indica si el recálculo manual ya está habilitado para una tesela."""
    created_at = _parse_db_timestamp(photo.get("created_at"))
    if created_at is None:
        return True

    seconds = int(
        current_app.config.get("COLLECTION_PHOTO_RETRY_ENABLE_SECONDS", 120)
    )
    age = datetime.now(timezone.utc) - created_at
    return age >= timedelta(seconds=max(0, seconds))


def update_zone_name(parcel_id: int, raw_name: str) -> str | None:
    """Actualiza el nombre persistido de una colección."""
    _ensure_parcela_name_column()

    normalized = " ".join((raw_name or "").split()).strip()
    if len(normalized) > COLLECTION_NAME_MAX_LENGTH:
        raise ValueError(
            _(
                "El nombre de la colección no puede"
                "superar %(count)s caracteres.",
                count=COLLECTION_NAME_MAX_LENGTH,
            )
        )

    database = get_db()
    cursor = database.execute(
        """
        UPDATE parcela
        SET
            nombre_coleccion = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE parcela_id = ?
        """,
        (normalized or None, parcel_id),
    )
    database.commit()

    if cursor.rowcount == 0:
        return None

    row = database.execute(
        """
        SELECT
            nombre_coleccion,
            pto_origen_lat,
            pto_origen_lng,
            pto_fin_lat,
            pto_fin_lng
        FROM parcela
        WHERE parcela_id = ?
        """,
        (parcel_id,),
    ).fetchone()

    return _zone_display_name_from_row(_row_to_dict(row))


def _parse_db_timestamp(value: str | None) -> datetime | None:
    """Convierte un timestamp SQLite a datetime UTC aware."""
    if not value:
        return None

    normalized = value.strip().replace("T", " ")
    try:
        parsed = datetime.strptime(normalized[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    return parsed.replace(tzinfo=timezone.utc)


def _stale_cutoff_string() -> str:
    """Devuelve el umbral temporal a partir del cual un processing es stale."""
    seconds = int(current_app.config.get("TRACE_WORKER_STALE_SECONDS", 600))
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, seconds))
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


def _photo_is_stale(photo: dict) -> bool:
    """Indica si una foto en processing lleva
        demasiado tiempo sin completarse."""
    if (photo.get("estado") or "").strip().lower() != "processing":
        return False

    started_at = _parse_db_timestamp(photo.get("started_at"))
    if started_at is None:
        return False

    seconds = int(current_app.config.get("TRACE_WORKER_STALE_SECONDS", 600))
    age = datetime.now(timezone.utc) - started_at
    return age >= timedelta(seconds=max(1, seconds))


def _photo_can_retry(photo: dict) -> bool:
    """Indica si una foto puede recalcularse manualmente ya."""
    return photo_retry_is_enabled(photo)


def _zone_photo_is_retryable(photo: dict) -> bool:
    """Indica si una tesela entra en el recálculo masivo de la zona."""
    status = (photo.get("estado") or "pending").strip().lower()

    if status == "failed":
        return True

    if status != "pending":
        return False

    return photo_retry_is_enabled(photo)


def zone_retry_is_enabled(photos: list[dict]) -> bool:
    """Indica si la zona puede recalcular pendientes o errores."""
    return any(_zone_photo_is_retryable(photo) for photo in (photos or []))


def get_collection_storage_root() -> str:
    """Devuelve la carpeta raíz de almacenamiento físico de la colección."""
    root = current_app.config["COLLECTION_STORAGE_ROOT"]
    os.makedirs(root, exist_ok=True)
    return root


def get_storage_abspath(relative_path: str | None) -> str | None:
    """
    Convierte una ruta relativa de la colección en ruta absoluta segura.

    Si la ruta es inválida o apunta fuera del root configurado, devuelve None.
    """
    if not relative_path:
        return None

    root = os.path.abspath(get_collection_storage_root())
    absolute_path = os.path.abspath(os.path.join(root, relative_path))

    if os.path.commonpath([root, absolute_path]) != root:
        return None

    return absolute_path


def _relative_storage_path(absolute_path: str) -> str:
    """Convierte una ruta absoluta de colección a una
        ruta relativa persistible."""
    root = os.path.abspath(get_collection_storage_root())
    return os.path.relpath(absolute_path, root).replace(os.sep, "/")


def _parcel_root_dir(parcel_id: int) -> str:
    """Devuelve la carpeta raíz física de una parcela."""
    return os.path.join(get_collection_storage_root(),
                        "parcelas", str(parcel_id))


def _parcel_tiles_dir(parcel_id: int) -> str:
    """Devuelve la carpeta física de teselas de una parcela."""
    return os.path.join(_parcel_root_dir(parcel_id), "tiles")


def _parcel_traces_dir(parcel_id: int) -> str:
    """Devuelve la carpeta física de resultados de trazas de una parcela."""
    return os.path.join(_parcel_root_dir(parcel_id), "traces")


def _parcel_preview_dir(parcel_id: int) -> str:
    """Devuelve la carpeta física de previews de una parcela."""
    return os.path.join(_parcel_root_dir(parcel_id), "preview")


def get_zone_preview_abspath(parcel_id: int) -> str:
    """Devuelve la ruta absoluta de la preview persistida de una parcela."""
    return os.path.join(_parcel_preview_dir(parcel_id), "zone_preview.jpg")


def save_zone_preview_bytes(parcel_id: int, image_bytes: bytes) -> str:
    """
    Guarda en disco la preview JPEG de una zona y devuelve su ruta absoluta.

    La escritura se hace sobre un fichero temporal y luego se reemplaza el
    destino final para evitar previews corruptas si algo falla a mitad.
    """
    os.makedirs(_parcel_preview_dir(parcel_id), exist_ok=True)

    preview_path = get_zone_preview_abspath(parcel_id)
    temp_path = f"{preview_path}.{uuid4().hex}.tmp"

    try:
        with open(temp_path, "wb") as preview_file:
            preview_file.write(image_bytes)
        os.replace(temp_path, preview_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return preview_path


def _parcel_delete_staging_dir() -> str:
    """Devuelve la carpeta temporal para borrados físicos seguros."""
    staging_dir = os.path.join(get_collection_storage_root(), ".deleted")
    os.makedirs(staging_dir, exist_ok=True)
    return staging_dir


def _stage_parcel_dir_for_delete(
    parcel_id: int,
) -> tuple[str | None, str | None]:
    """
    Mueve temporalmente la carpeta física de una parcela antes de borrarla.

    Esto permite restaurarla si el borrado en SQLite falla antes del commit.
    """
    parcel_root = _parcel_root_dir(parcel_id)
    if not os.path.isdir(parcel_root):
        return None, None

    staged_path = os.path.join(
        _parcel_delete_staging_dir(),
        f"parcela_{parcel_id}_{uuid4().hex}",
    )
    os.replace(parcel_root, staged_path)
    return parcel_root, staged_path


def _photo_trace_status(photo: dict) -> str:
    """
    Deriva el estado visual de trazas para una foto.

    Se apoya en el campo persistido estado para que la galería refleje
    pending / processing / completed sin lógica duplicada en frontend.
    """
    status = (photo.get("estado") or "pending").strip().lower()
    if status in {"completed", "processing"}:
        return status
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

    En esta versión solo guarda metadata en SQLite. La descarga física de las
    teselas se difiere al worker de trazas para no bloquear la petición web.
    """
    if status not in ALLOWED_ZONE_STATUSES:
        raise ValueError("Estado de zona no soportado.")

    _ensure_parcela_name_column()

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
                estado,
                error_message,
                started_at,
                finished_at,
                attempt_count,
                tile_id,
                row_index,
                col_index,
                filename,
                width,
                height,
                bbox3857_json,
                bounds_json,
                source_id
            ) VALUES (
                ?, DATE('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
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
                "pending",
                None,
                None,
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
    _ensure_parcela_name_column()

    database = get_db()
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    offset = (page - 1) * per_page
    search = (search or "").strip()
    like = f"%{search}%"

    where_clause = """
        WHERE (
            ? = ''
            OR COALESCE(p.nombre_coleccion, '') LIKE ?
            OR p.source_label LIKE ?
            OR p.fecha LIKE ?
            OR CAST(p.pto_origen_lat AS TEXT) LIKE ?
            OR CAST(p.pto_origen_lng AS TEXT) LIKE ?
            OR CAST(p.pto_fin_lat AS TEXT) LIKE ?
            OR CAST(p.pto_fin_lng AS TEXT) LIKE ?
        )
    """
    params = (search, like, like, like, like, like, like, like)

    total = database.execute(
        f"SELECT COUNT(*) AS total FROM parcela p {where_clause}",
        params,
    ).fetchone()["total"]

    rows = database.execute(
        f"""
        SELECT
            p.parcela_id,
            p.nombre_coleccion,
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
            SUM(CASE WHEN f.estado = 'completed' THEN 1 ELSE 0 END)
                AS completed_tiles,
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
        item["tile_count"] = int(item.get("tile_count") or 0)
        item["completed_tiles"] = int(item.get("completed_tiles") or 0)
        item["origin"] = {
            "lat": float(item["pto_origen_lat"]),
            "lng": float(item["pto_origen_lng"]),
        }
        item["destination"] = {
            "lat": float(item["pto_fin_lat"]),
            "lng": float(item["pto_fin_lng"]),
        }
        item["display_name"] = _zone_display_name_from_row(item)
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
    _ensure_parcela_name_column()

    database = get_db()

    parcel_row = database.execute(
        """
        SELECT
            parcela_id,
            nombre_coleccion,
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
    parcel["display_name"] = _zone_display_name_from_row(parcel)

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
            estado,
            error_message,
            started_at,
            finished_at,
            attempt_count,
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
        photo["is_stale"] = _photo_is_stale(photo)
        photo["can_retry"] = _photo_can_retry(photo)
        photos.append(photo)

    parcel["tile_count"] = len(photos)
    parcel["preview_photo_id"] = photos[0]["foto_id"] if photos else None
    parcel["photos"] = photos
    parcel["completed_tiles"] = sum(
        1 for photo in photos if photo.get("estado") == "completed"
    )
    parcel["can_retry_all"] = zone_retry_is_enabled(photos)
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
        "display_name": detail["display_name"],
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
            estado,
            error_message,
            started_at,
            finished_at,
            attempt_count,
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
    """
    Elimina una parcela, sus fotos asociadas y su almacenamiento físico.

    La carpeta de la parcela se mueve primero a una zona temporal. Si el
    borrado en SQLite falla, se intenta restaurar. Si el commit tiene éxito,
    la carpeta temporal se purga definitivamente.
    """
    database = get_db()
    row = database.execute(
        "SELECT parcela_id FROM parcela WHERE parcela_id = ?",
        (parcel_id,),
    ).fetchone()

    if row is None:
        return False

    parcel_root = None
    staged_path = None
    cursor = None

    try:
        parcel_root, staged_path = _stage_parcel_dir_for_delete(parcel_id)

        cursor = database.execute(
            "DELETE FROM parcela WHERE parcela_id = ?",
            (parcel_id,),
        )
        database.commit()
    except Exception as exc:
        database.rollback()

        if parcel_root and staged_path and os.path.exists(staged_path):
            try:
                os.replace(staged_path, parcel_root)
            except OSError:
                current_app.logger.exception(
                    "No se pudo restaurar la carpeta física de la parcela %s "
                    "tras un fallo de borrado.",
                    parcel_id,
                )

        raise ZoneDeleteError(
            _(
                "No se ha podido eliminar completamente la zona. "
                "Inténtalo de nuevo."
            )
        ) from exc

    if staged_path and os.path.exists(staged_path):
        try:
            shutil.rmtree(staged_path)
        except OSError:
            current_app.logger.exception(
                "No se pudo purgar la carpeta temporal de la parcela %s.",
                parcel_id,
            )

    return bool(cursor and cursor.rowcount > 0)


def save_photo_traces_result(photo: dict, traces: dict) -> str:
    """Guarda el resultado JSON de trazas de una foto
        y devuelve su ruta relativa."""
    os.makedirs(_parcel_traces_dir(photo["parcela_id"]), exist_ok=True)
    filename_root, _ext = os.path.splitext(photo["filename"])
    traces_filename = f"{filename_root}_traces.json"
    traces_absolute_path = os.path.join(
        _parcel_traces_dir(photo["parcela_id"]),
        traces_filename,
    )

    with open(traces_absolute_path, "w", encoding="utf-8") as traces_file:
        json.dump(traces, traces_file, ensure_ascii=False, indent=2)

    return _relative_storage_path(traces_absolute_path)


def materialize_photo_tile(photo: dict) -> str:
    """
    Garantiza que la tesela de una foto exista físicamente en disco.

    Si ya existe localmente, devuelve su ruta absoluta.
    Si no existe, la descarga desde la fuente cartográfica, la guarda en
    instance/collection y actualiza ruta_foto en SQLite.
    """
    local_path = get_storage_abspath(photo.get("ruta_foto"))
    if local_path and os.path.exists(local_path):
        return local_path

    from .visor import _visor_fetch_tile_bytes, _visor_source_by_id

    source = _visor_source_by_id(photo["source_id"])
    if source is None:
        raise RuntimeError(_("La fuente de la tesela ya no está disponible."))

    bbox = photo["bbox3857"]
    bbox3857 = (
        float(bbox["xmin"]),
        float(bbox["ymin"]),
        float(bbox["xmax"]),
        float(bbox["ymax"]),
    )

    tile_bytes = _visor_fetch_tile_bytes(
        source,
        bbox3857,
        int(photo["width"]),
        int(photo["height"]),
    )

    os.makedirs(_parcel_tiles_dir(photo["parcela_id"]), exist_ok=True)
    absolute_path = os.path.join(
        _parcel_tiles_dir(photo["parcela_id"]),
        photo["filename"],
    )

    with open(absolute_path, "wb") as output_file:
        output_file.write(tile_bytes)

    relative_path = _relative_storage_path(absolute_path)

    database = get_db()
    database.execute(
        """
        UPDATE foto
        SET ruta_foto = ?
        WHERE foto_id = ?
        """,
        (relative_path, photo["foto_id"]),
    )
    database.commit()

    photo["ruta_foto"] = relative_path
    return absolute_path


def claim_pending_photos(*, limit: int = 1) -> list[dict]:
    """
    Reclama fotos pendientes o processing stale y las marca como processing.

    Así se recuperan automáticamente teselas que se hubieran quedado colgadas
    tras un reinicio, corte del proceso o inferencia interrumpida.
    """
    database = get_db()
    limit = max(1, int(limit))
    stale_cutoff = _stale_cutoff_string()

    database.execute("BEGIN IMMEDIATE")
    id_rows = database.execute(
        """
        SELECT foto_id
        FROM foto
        WHERE estado = 'pending'
           OR (
               estado = 'processing'
               AND started_at IS NOT NULL
               AND started_at <= ?
           )
        ORDER BY
            CASE WHEN estado = 'processing' THEN 0 ELSE 1 END,
            foto_id ASC
        LIMIT ?
        """,
        (stale_cutoff, limit),
    ).fetchall()

    photo_ids = [row["foto_id"] for row in id_rows]
    if not photo_ids:
        database.commit()
        return []

    placeholders = ",".join("?" for _ in photo_ids)
    database.execute(
        f"""
        UPDATE foto
        SET
            estado = 'processing',
            started_at = CURRENT_TIMESTAMP,
            finished_at = NULL,
            error_message = NULL,
            attempt_count = COALESCE(attempt_count, 0) + 1
        WHERE foto_id IN ({placeholders})
        """,
        photo_ids,
    )
    database.commit()

    photos = [get_photo(photo_id) for photo_id in photo_ids]
    for photo in photos:
        if photo is not None:
            refresh_parcel_status(photo["parcela_id"])

    return [photo for photo in photos if photo is not None]


def mark_photo_completed(photo_id: int, trace_relative_path: str) -> None:
    """Marca una foto como completada y actualiza el estado de su parcela."""
    database = get_db()
    row = database.execute(
        "SELECT parcela_id FROM foto WHERE foto_id = ?",
        (photo_id,),
    ).fetchone()
    if row is None:
        return

    database.execute(
        """
        UPDATE foto
        SET
            trazas = 1,
            estado = 'completed',
            ruta_trazas = ?,
            error_message = NULL,
            finished_at = CURRENT_TIMESTAMP
        WHERE foto_id = ?
        """,
        (trace_relative_path, photo_id),
    )
    database.commit()
    refresh_parcel_status(row["parcela_id"])


def mark_photo_failed(photo_id: int, message: str) -> None:
    """Marca una foto como fallida y actualiza el estado de su parcela."""
    database = get_db()
    row = database.execute(
        "SELECT parcela_id FROM foto WHERE foto_id = ?",
        (photo_id,),
    ).fetchone()
    if row is None:
        return

    database.execute(
        """
        UPDATE foto
        SET
            trazas = 0,
            estado = 'failed',
            error_message = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE foto_id = ?
        """,
        (message[:1000], photo_id),
    )
    database.commit()
    refresh_parcel_status(row["parcela_id"])


def refresh_parcel_status(parcel_id: int) -> str:
    """Recalcula el estado agregado de una parcela a partir de sus fotos."""
    database = get_db()
    summary = database.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN estado = 'pending' THEN 1 ELSE 0 END)
                AS pending_count,
            SUM(CASE WHEN estado = 'processing' THEN 1 ELSE 0 END)
                AS processing_count,
            SUM(CASE WHEN estado = 'completed' THEN 1 ELSE 0 END)
                AS completed_count,
            SUM(CASE WHEN estado = 'failed' THEN 1 ELSE 0 END) AS failed_count
        FROM foto
        WHERE parcela_id = ?
        """,
        (parcel_id,),
    ).fetchone()

    total = int(summary["total"] or 0)
    pending_count = int(summary["pending_count"] or 0)
    processing_count = int(summary["processing_count"] or 0)
    completed_count = int(summary["completed_count"] or 0)
    failed_count = int(summary["failed_count"] or 0)

    if total == 0 or pending_count == total:
        status = "pending"
    elif completed_count == total:
        status = "completed"
    elif failed_count == total:
        status = "failed"
    elif processing_count > 0:
        status = "processing"
    elif pending_count > 0 and completed_count > 0:
        status = "processing"
    elif pending_count > 0 and failed_count > 0:
        status = "processing"
    elif failed_count > 0 and completed_count > 0:
        status = "failed"
    else:
        status = "processing"

    database.execute(
        """
        UPDATE parcela
        SET
            estado = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE parcela_id = ?
        """,
        (status, parcel_id),
    )
    database.commit()
    return status


def get_zone_status_summary(parcel_id: int) -> dict | None:
    """Devuelve un resumen de estado de una parcela."""
    _ensure_parcela_name_column()

    database = get_db()
    row = database.execute(
        """
        SELECT
            p.parcela_id,
            p.estado,
            p.nombre_coleccion,
            p.pto_origen_lat,
            p.pto_origen_lng,
            p.pto_fin_lat,
            p.pto_fin_lng,
            COUNT(f.foto_id) AS tile_count,
            SUM(CASE WHEN f.estado = 'pending' THEN 1 ELSE 0 END)
                AS pending_tiles,
            SUM(CASE WHEN f.estado = 'processing' THEN 1 ELSE 0 END)
                AS processing_tiles,
            SUM(CASE WHEN f.estado = 'completed' THEN 1 ELSE 0 END)
                AS completed_tiles,
            SUM(CASE WHEN f.estado = 'failed' THEN 1 ELSE 0 END)
                AS failed_tiles
        FROM parcela p
        LEFT JOIN foto f ON f.parcela_id = p.parcela_id
        WHERE p.parcela_id = ?
        GROUP BY p.parcela_id
        """,
        (parcel_id,),
    ).fetchone()

    if row is None:
        return None

    summary = _row_to_dict(row)
    for key in (
        "tile_count",
        "pending_tiles",
        "processing_tiles",
        "completed_tiles",
        "failed_tiles",
    ):
        summary[key] = int(summary.get(key) or 0)

    summary["display_name"] = _zone_display_name_from_row(summary)
    return summary


def list_zone_status_summaries(parcel_ids: list[int]) -> list[dict]:
    """Devuelve el resumen de estado para varias parcelas."""
    summaries = []
    for parcel_id in parcel_ids:
        summary = get_zone_status_summary(parcel_id)
        if summary is not None:
            summaries.append(summary)
    return summaries


def get_zone_live_status(parcel_id: int) -> dict | None:
    """
    Devuelve el estado vivo completo de una parcela y sus fotos.

    Se usa para polling en galería y combina resumen agregado con el estado
    individual de cada foto.
    """
    summary = get_zone_status_summary(parcel_id)
    if summary is None:
        return None

    database = get_db()
    photo_rows = database.execute(
        """
        SELECT
            foto_id,
            estado,
            trazas,
            started_at,
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
        photo["trace_status"] = _photo_trace_status(photo)
        photo["is_stale"] = _photo_is_stale(photo)
        photo["can_retry"] = _photo_can_retry(photo)
        photos.append(photo)

    summary["photos"] = photos
    summary["can_retry_all"] = zone_retry_is_enabled(photos)
    return summary


def retry_zone_pending_and_failed(parcel_id: int) -> int:
    """
    Marca para recalcular solo las teselas pending o failed de una zona.

    Las teselas completed no se tocan. Las processing tampoco.
    """
    detail = get_zone_detail(parcel_id)
    if detail is None:
        return 0

    photos = detail.get("photos") or []
    if not zone_retry_is_enabled(photos):
        return 0

    target_photos = [
        photo for photo in photos
        if (photo.get("estado") or "pending").strip().lower()
        in {"pending", "failed"}
    ]
    if not target_photos:
        return 0

    for photo in target_photos:
        trace_absolute_path = get_storage_abspath(photo.get("ruta_trazas"))
        if trace_absolute_path and os.path.exists(trace_absolute_path):
            try:
                os.remove(trace_absolute_path)
            except OSError:
                pass

    photo_ids = [int(photo["foto_id"]) for photo in target_photos]
    placeholders = ",".join("?" for _ in photo_ids)

    database = get_db()
    database.execute(
        f"""
        UPDATE foto
        SET
            trazas = 0,
            estado = 'pending',
            ruta_trazas = NULL,
            error_message = NULL,
            started_at = NULL,
            finished_at = NULL
        WHERE foto_id IN ({placeholders})
        """,
        photo_ids,
    )
    database.commit()
    refresh_parcel_status(parcel_id)
    return len(photo_ids)


def retry_photo(photo_id: int) -> bool:
    """
    Devuelve una foto a pending para reintentar su procesamiento.

    Se permite especialmente para fotos failed o processing stale.
    """
    database = get_db()
    row = database.execute(
        """
        SELECT foto_id, parcela_id, estado, ruta_trazas
        FROM foto
        WHERE foto_id = ?
        """,
        (photo_id,),
    ).fetchone()

    if row is None:
        return False

    trace_absolute_path = get_storage_abspath(row["ruta_trazas"])
    if trace_absolute_path and os.path.exists(trace_absolute_path):
        try:
            os.remove(trace_absolute_path)
        except OSError:
            pass

    database.execute(
        """
        UPDATE foto
        SET
            trazas = 0,
            estado = 'pending',
            ruta_trazas = NULL,
            error_message = NULL,
            started_at = NULL,
            finished_at = NULL
        WHERE foto_id = ?
        """,
        (photo_id,),
    )
    database.commit()
    refresh_parcel_status(row["parcela_id"])
    return True
