"""
===============================================================================
Acceso a datos para la colección de imágenes mediante SQLAlchemy.

Este módulo encapsula la persistencia de parcelas y fotos para que las rutas de
Flask, el visor y el worker reutilicen una única capa de acceso a datos. Todas
las operaciones de lectura y escritura pasan por los modelos SQLAlchemy.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from math import ceil
import shutil
from urllib.parse import urlparse
from uuid import uuid4

from flask import current_app, has_request_context, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import String, cast, func, or_, select

from .db import db
from .model_store import get_active_model
from .models import Foto, Parcela

DEFAULT_SYSTEM_USER_ID = 1
ALLOWED_ZONE_STATUSES = {"pending", "processing", "completed", "failed"}
COLLECTION_NAME_MAX_LENGTH = 120


class ZoneDeleteError(RuntimeError):
    """Error controlado al eliminar una zona de la colección."""


def _now_db_string() -> str:
    """Devuelve un timestamp compatible con los valores SQLite existentes."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


def _parcel_to_dict(parcel: Parcela) -> dict:
    """Convierte una instancia Parcela en el contrato dict existente."""
    return {
        "parcela_id": parcel.parcela_id,
        "nombre_coleccion": parcel.nombre_coleccion,
        "usuario_id": parcel.usuario_id,
        "tamano_metros": parcel.tamano_metros,
        "pto_origen_lat": parcel.pto_origen_lat,
        "pto_origen_lng": parcel.pto_origen_lng,
        "pto_fin_lat": parcel.pto_fin_lat,
        "pto_fin_lng": parcel.pto_fin_lng,
        "fecha": parcel.fecha,
        "source_id": parcel.source_id,
        "source_label": parcel.source_label,
        "requested_resolution": parcel.requested_resolution,
        "actual_resolution": parcel.actual_resolution,
        "tile_width": parcel.tile_width,
        "tile_height": parcel.tile_height,
        "estado": parcel.estado,
        "created_at": parcel.created_at,
        "updated_at": parcel.updated_at,
    }


def _photo_to_dict(photo: Foto) -> dict:
    """Convierte una instancia Foto en el contrato dict existente."""
    return {
        "foto_id": photo.foto_id,
        "parcela_id": photo.parcela_id,
        "modelo_id": photo.modelo_id,
        "modelo_nombre": (
            photo.modelo.nombre_modelo
            if photo.modelo is not None
            else None
        ),
        "fecha_foto": photo.fecha_foto,
        "resolucion_valor": photo.resolucion_valor,
        "resolucion_unidad": photo.resolucion_unidad,
        "longitud": photo.longitud,
        "latitud": photo.latitud,
        "ruta_foto": photo.ruta_foto,
        "ruta_trazas": photo.ruta_trazas,
        "trazas": photo.trazas,
        "estado": photo.estado,
        "error_message": photo.error_message,
        "started_at": photo.started_at,
        "finished_at": photo.finished_at,
        "attempt_count": photo.attempt_count,
        "tile_id": photo.tile_id,
        "row_index": photo.row_index,
        "col_index": photo.col_index,
        "filename": photo.filename,
        "width": photo.width,
        "height": photo.height,
        "bbox3857_json": photo.bbox3857_json,
        "bounds_json": photo.bounds_json,
        "source_id": photo.parcela.source_id if photo.parcela is not None else None,
        "created_at": photo.created_at,
    }


def _photo_contract_from_model(photo: Foto) -> dict:
    """Devuelve una foto con JSONs deserializados y campos calculados."""
    item = _photo_to_dict(photo)
    item["bbox3857"] = _json_loads(item.pop("bbox3857_json", "{}"), {})
    item["bounds"] = _json_loads(item.pop("bounds_json", "{}"), {})
    item["trace_status"] = _photo_trace_status(item)
    item["is_stale"] = _photo_is_stale(item)
    item["can_retry"] = _photo_can_retry(item)
    return item


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
    normalized = " ".join((raw_name or "").split()).strip()
    if len(normalized) > COLLECTION_NAME_MAX_LENGTH:
        raise ValueError(
            _(
                "El nombre de la colección no puede "
                "superar %(count)s caracteres.",
                count=COLLECTION_NAME_MAX_LENGTH,
            )
        )

    parcel = db.session.get(Parcela, parcel_id)
    if parcel is None:
        return None

    parcel.nombre_coleccion = normalized or None
    parcel.updated_at = _now_db_string()
    db.session.commit()

    return _zone_display_name_from_row(_parcel_to_dict(parcel))


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
    """Indica si una foto en processing lleva demasiado tiempo sin completarse."""
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
    """Convierte una ruta absoluta de colección a una ruta relativa."""
    root = os.path.abspath(get_collection_storage_root())
    return os.path.relpath(absolute_path, root).replace(os.sep, "/")


def _parcel_root_dir(parcel_id: int) -> str:
    """Devuelve la carpeta raíz física de una parcela."""
    return os.path.join(get_collection_storage_root(), "parcelas", str(parcel_id))


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

    Esto permite restaurarla si el borrado en base de datos falla antes del
    commit.
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

    Se apoya en el campo persistido estado para que la galería refleje pending,
    processing o completed sin lógica duplicada en frontend.
    """
    status = (photo.get("estado") or "pending").strip().lower()
    if status in {"completed", "processing"}:
        return status
    return "pending"


def _zone_trace_status(photos: list[dict]) -> str:
    """Devuelve el estado agregado de trazas de una colección."""
    if not photos:
        return "pending"

    if all(
        (photo.get("estado") or "").strip().lower() == "completed"
        and bool(photo.get("ruta_trazas"))
        for photo in photos
    ):
        return "completed"

    if any(
        (photo.get("estado") or "").strip().lower() == "failed"
        for photo in photos
    ):
        return "failed"

    if any(
        (photo.get("estado") or "").strip().lower() == "processing"
        for photo in photos
    ):
        return "processing"

    return "pending"


def get_default_user_id() -> int:
    """Devuelve el usuario propietario aplicable a nuevas zonas."""
    if has_request_context():
        user = current_user._get_current_object()
        if user is not None and getattr(user, "is_authenticated", False):
            return int(user.usuario_id)

    return DEFAULT_SYSTEM_USER_ID


def _current_collection_owner_id() -> int | None:
    """Devuelve el propietario efectivo de la colección visible actual."""
    if not has_request_context():
        return None

    return get_default_user_id()


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

    En esta versión solo guarda metadata. La descarga física de las teselas se
    difiere al worker de trazas para no bloquear la petición web.
    """
    if status not in ALLOWED_ZONE_STATUSES:
        raise ValueError("Estado de zona no soportado.")

    south, west, north, east = bbox4326
    xmin, ymin, xmax, ymax = bbox3857
    width_m = max(0.0, xmax - xmin)
    height_m = max(0.0, ymax - ymin)
    area_m2 = width_m * height_m

    parcel = Parcela(
        usuario_id=get_default_user_id(),
        tamano_metros=area_m2,
        pto_origen_lat=float(origin_point["lat"]),
        pto_origen_lng=float(origin_point["lng"]),
        pto_fin_lat=float(destination_point["lat"]),
        pto_fin_lng=float(destination_point["lng"]),
        source_id=source["id"],
        source_label=source["label"],
        requested_resolution=float(requested_resolution),
        actual_resolution=float(actual_resolution),
        tile_width=int(tile_width),
        tile_height=int(tile_height),
        estado=status,
    )
    db.session.add(parcel)
    db.session.flush()

    today_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for tile in tiles:
        bounds = tile.get("bounds", {})
        bbox_tile = tile.get("bbox3857", {})
        center_lat, center_lng = _center_from_bounds(bounds)
        db.session.add(
            Foto(
                parcela_id=int(parcel.parcela_id),
                modelo_id=None,
                fecha_foto=today_label,
                resolucion_valor=float(actual_resolution),
                resolucion_unidad="m/px",
                longitud=center_lng,
                latitud=center_lat,
                ruta_foto=_route_path_only(tile.get("download_url", "")),
                ruta_trazas=None,
                trazas=0,
                estado="pending",
                error_message=None,
                started_at=None,
                finished_at=None,
                attempt_count=0,
                tile_id=tile["id"],
                row_index=int(tile["row"]),
                col_index=int(tile["col"]),
                filename=tile["filename"],
                width=int(tile["width"]),
                height=int(tile["height"]),
                bbox3857_json=json.dumps(bbox_tile, ensure_ascii=False),
                bounds_json=json.dumps(bounds, ensure_ascii=False),
            )
        )

    db.session.commit()
    return int(parcel.parcela_id)


def list_zones(*, page: int = 1, per_page: int = 10, search: str = "") -> dict:
    """Devuelve un listado paginado de parcelas de la colección."""
    owner_id = _current_collection_owner_id()
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    offset = (page - 1) * per_page
    search = (search or "").strip()

    if owner_id is None:
        return {
            "zones": [],
            "page": page,
            "per_page": per_page,
            "total": 0,
            "total_pages": 1,
            "search": search,
        }

    filters = [Parcela.usuario_id == owner_id]
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(func.coalesce(Parcela.nombre_coleccion, "")).like(
                    like
                ),
                func.lower(Parcela.source_label).like(like),
                func.lower(Parcela.fecha).like(like),
                func.lower(cast(Parcela.pto_origen_lat, String)).like(like),
                func.lower(cast(Parcela.pto_origen_lng, String)).like(like),
                func.lower(cast(Parcela.pto_fin_lat, String)).like(like),
                func.lower(cast(Parcela.pto_fin_lng, String)).like(like),
            )
        )

    total = int(
        db.session.execute(
            select(func.count(Parcela.parcela_id)).where(*filters)
        ).scalar_one()
    )

    parcels = db.session.execute(
        select(Parcela)
        .where(*filters)
        .order_by(Parcela.parcela_id.desc())
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    zones = []
    for parcel in parcels:
        photos = db.session.execute(
            select(Foto).where(Foto.parcela_id == parcel.parcela_id)
        ).scalars().all()
        item = _parcel_to_dict(parcel)
        item["tile_count"] = len(photos)
        item["completed_tiles"] = sum(
            1 for photo in photos if photo.estado == "completed"
        )
        item["preview_foto_id"] = min(
            (photo.foto_id for photo in photos),
            default=None,
        )
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
    stmt = select(Parcela).where(Parcela.parcela_id == parcel_id)
    owner_id = _current_collection_owner_id()
    if owner_id is not None:
        stmt = stmt.where(Parcela.usuario_id == owner_id)

    parcel_model = db.session.execute(stmt).scalar_one_or_none()
    if parcel_model is None:
        return None

    parcel = _parcel_to_dict(parcel_model)
    parcel["bbox"] = {
        "south": float(parcel["pto_origen_lat"]),
        "west": float(parcel["pto_origen_lng"]),
        "north": float(parcel["pto_fin_lat"]),
        "east": float(parcel["pto_fin_lng"]),
    }
    parcel["origin"] = {
        "lat": float(parcel["pto_origen_lat"]),
        "lng": float(parcel["pto_origen_lng"]),
    }
    parcel["destination"] = {
        "lat": float(parcel["pto_fin_lat"]),
        "lng": float(parcel["pto_fin_lng"]),
    }
    parcel["display_name"] = _zone_display_name_from_row(parcel)

    photo_models = db.session.execute(
        select(Foto)
        .where(Foto.parcela_id == parcel_id)
        .order_by(Foto.row_index.asc(), Foto.col_index.asc(), Foto.foto_id.asc())
    ).scalars().all()

    photos = [_photo_contract_from_model(photo) for photo in photo_models]
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

    trace_status = _zone_trace_status(detail["photos"])
    can_draw_traces = trace_status == "completed"

    tiles = []
    for photo in detail["photos"]:
        tiles.append(
            {
                "id": photo["tile_id"],
                "row": photo["row_index"],
                "col": photo["col_index"],
                "photo_id": photo["foto_id"],
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
                "status": photo.get("estado") or "pending",
                "trace_status": photo.get("trace_status") or "pending",
                "traces_url": url_for(
                    "trazas.collection_photo_traces",
                    photo_id=photo["foto_id"],
                ),
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
        "trace_status": trace_status,
        "can_draw_traces": can_draw_traces,
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
            "trace_status": trace_status,
            "can_draw_traces": can_draw_traces,
            "warnings": [],
            "tiles": tiles,
        },
    }


def get_photo(
    photo_id: int,
    *,
    enforce_current_user: bool = True,
) -> dict | None:
    """Recupera una foto concreta de la colección."""
    stmt = select(Foto).where(Foto.foto_id == photo_id)

    if enforce_current_user:
        owner_id = _current_collection_owner_id()
        if owner_id is None:
            return None
        stmt = stmt.join(Parcela).where(Parcela.usuario_id == owner_id)

    photo_model = db.session.execute(stmt).scalar_one_or_none()
    if photo_model is None:
        return None

    item = _photo_to_dict(photo_model)
    item["bbox3857"] = _json_loads(item.pop("bbox3857_json", "{}"), {})
    item["bounds"] = _json_loads(item.pop("bounds_json", "{}"), {})
    return item


def delete_zone(parcel_id: int) -> bool:
    """
    Elimina una parcela, sus fotos asociadas y su almacenamiento físico.

    La carpeta de la parcela se mueve primero a una zona temporal. Si el
    borrado en base de datos falla, se intenta restaurar. Si el commit tiene
    éxito, la carpeta temporal se purga definitivamente.
    """
    owner_id = _current_collection_owner_id()
    if owner_id is None:
        return False

    parcel = db.session.execute(
        select(Parcela).where(
            Parcela.parcela_id == parcel_id,
            Parcela.usuario_id == owner_id,
        )
    ).scalar_one_or_none()

    if parcel is None:
        return False

    parcel_root = None
    staged_path = None

    try:
        parcel_root, staged_path = _stage_parcel_dir_for_delete(parcel_id)
        db.session.delete(parcel)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()

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

    return True


def save_photo_traces_result(photo: dict, traces: dict) -> str:
    """Guarda el resultado JSON de trazas de una foto y devuelve su ruta."""
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

    Si ya existe localmente, devuelve su ruta absoluta. Si no existe, la
    descarga desde la fuente cartográfica, la guarda en instance/collection y
    actualiza ruta_foto mediante SQLAlchemy.
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

    photo_model = db.session.get(Foto, photo["foto_id"])
    if photo_model is not None:
        photo_model.ruta_foto = relative_path
        db.session.commit()

    photo["ruta_foto"] = relative_path
    return absolute_path


def claim_pending_photos(*, limit: int = 1) -> list[dict]:
    """
    Reclama fotos pendientes o processing stale y las marca como processing.

    Así se recuperan automáticamente teselas que se hubieran quedado colgadas
    tras un reinicio, corte del proceso o inferencia interrumpida.
    """
    limit = max(1, int(limit))
    stale_cutoff = _stale_cutoff_string()

    photos = db.session.execute(
        select(Foto)
        .where(
            or_(
                Foto.estado == "pending",
                (Foto.estado == "processing")
                & (Foto.started_at.is_not(None))
                & (Foto.started_at <= stale_cutoff),
            )
        )
        .order_by(
            (Foto.estado == "processing").desc(),
            Foto.foto_id.asc(),
        )
        .limit(limit)
    ).scalars().all()

    if not photos:
        return []

    now_label = _now_db_string()
    parcel_ids = set()
    photo_ids = []
    for photo in photos:
        photo.estado = "processing"
        photo.started_at = now_label
        photo.finished_at = None
        photo.error_message = None
        photo.attempt_count = int(photo.attempt_count or 0) + 1
        parcel_ids.add(int(photo.parcela_id))
        photo_ids.append(int(photo.foto_id))

    db.session.commit()

    for parcel_id in parcel_ids:
        refresh_parcel_status(parcel_id)

    return [
        photo for photo_id in photo_ids
        if (photo := get_photo(photo_id, enforce_current_user=False)) is not None
    ]


def mark_photo_completed(photo_id: int, trace_relative_path: str) -> None:
    """Marca una foto como completada y actualiza el estado de su parcela."""
    photo = db.session.get(Foto, photo_id)
    if photo is None:
        return

    active_model = get_active_model()

    parcel_id = int(photo.parcela_id)
    if active_model is not None:
        photo.modelo_id = int(active_model.modelo_id)
    photo.trazas = 1
    photo.estado = "completed"
    photo.ruta_trazas = trace_relative_path
    photo.error_message = None
    photo.finished_at = _now_db_string()
    db.session.commit()
    refresh_parcel_status(parcel_id)


def mark_photo_failed(photo_id: int, message: str) -> None:
    """Marca una foto como fallida y actualiza el estado de su parcela."""
    photo = db.session.get(Foto, photo_id)
    if photo is None:
        return

    parcel_id = int(photo.parcela_id)
    photo.modelo_id = None
    photo.trazas = 0
    photo.estado = "failed"
    photo.error_message = message[:1000]
    photo.finished_at = _now_db_string()
    db.session.commit()
    refresh_parcel_status(parcel_id)


def refresh_parcel_status(parcel_id: int) -> str:
    """Recalcula el estado agregado de una parcela a partir de sus fotos."""
    parcel = db.session.get(Parcela, parcel_id)
    if parcel is None:
        return "pending"

    statuses = db.session.execute(
        select(Foto.estado).where(Foto.parcela_id == parcel_id)
    ).scalars().all()

    total = len(statuses)
    pending_count = statuses.count("pending")
    processing_count = statuses.count("processing")
    completed_count = statuses.count("completed")
    failed_count = statuses.count("failed")

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

    parcel.estado = status
    parcel.updated_at = _now_db_string()
    db.session.commit()
    return status


def get_zone_status_summary(parcel_id: int) -> dict | None:
    """Devuelve un resumen de estado de una parcela."""
    stmt = select(Parcela).where(Parcela.parcela_id == parcel_id)
    owner_id = _current_collection_owner_id()
    if owner_id is not None:
        stmt = stmt.where(Parcela.usuario_id == owner_id)

    parcel = db.session.execute(stmt).scalar_one_or_none()
    if parcel is None:
        return None

    photos = db.session.execute(
        select(Foto.estado).where(Foto.parcela_id == parcel_id)
    ).scalars().all()

    summary = _parcel_to_dict(parcel)
    summary["tile_count"] = len(photos)
    summary["pending_tiles"] = photos.count("pending")
    summary["processing_tiles"] = photos.count("processing")
    summary["completed_tiles"] = photos.count("completed")
    summary["failed_tiles"] = photos.count("failed")
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

    photo_models = db.session.execute(
        select(Foto)
        .where(Foto.parcela_id == parcel_id)
        .order_by(Foto.row_index.asc(), Foto.col_index.asc(), Foto.foto_id.asc())
    ).scalars().all()

    photos = []
    for photo_model in photo_models:
        photo = _photo_to_dict(photo_model)
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
    photo_models = db.session.execute(
        select(Foto).where(Foto.foto_id.in_(photo_ids))
    ).scalars().all()

    for photo in photo_models:
        photo.modelo_id = None
        photo.trazas = 0
        photo.estado = "pending"
        photo.ruta_trazas = None
        photo.error_message = None
        photo.started_at = None
        photo.finished_at = None

    db.session.commit()
    refresh_parcel_status(parcel_id)
    return len(photo_ids)


def retry_photo(photo_id: int) -> bool:
    """
    Devuelve una foto a pending para reintentar su procesamiento.

    Se permite especialmente para fotos failed o processing stale.
    """
    photo = db.session.get(Foto, photo_id)
    if photo is None:
        return False

    parcel_id = int(photo.parcela_id)
    trace_absolute_path = get_storage_abspath(photo.ruta_trazas)
    if trace_absolute_path and os.path.exists(trace_absolute_path):
        try:
            os.remove(trace_absolute_path)
        except OSError:
            pass

    photo.modelo_id = None
    photo.trazas = 0
    photo.estado = "pending"
    photo.ruta_trazas = None
    photo.error_message = None
    photo.started_at = None
    photo.finished_at = None
    db.session.commit()
    refresh_parcel_status(parcel_id)
    return True
