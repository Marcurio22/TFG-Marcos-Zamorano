"""
===============================================================================
Rutas de la colección de imágenes y galerías de teselas.

Este módulo define la nueva pantalla persistente de colección, así como las
vistas auxiliares de galería, preview, descarga ZIP y eliminación de zonas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from urllib.parse import urlparse

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_babel import gettext as _
from PIL import Image
from werkzeug.utils import secure_filename

from .collection_store import (
    ZoneDeleteError,
    delete_zone,
    get_photo,
    get_storage_abspath,
    get_zone_detail,
    get_zone_live_status,
    get_zone_preview_abspath,
    list_zone_status_summaries,
    list_zones,
    photo_retry_is_enabled,
    retry_photo,
    retry_zone_pending_and_failed,
    save_zone_preview_bytes,
    update_zone_name,
    zone_retry_is_enabled,
)
from .visor import (
    _visor_fetch_tile_bytes,
    _visor_source_by_id,
)

COLLECTION_PER_PAGE_OPTIONS = (10, 25, 50)
COLLECTION_PREVIEW_MAX_WIDTH = 1024
COLLECTION_PREVIEW_MAX_HEIGHT = 640
_PREVIEW_RESAMPLING = getattr(
    getattr(Image, "Resampling", Image),
    "LANCZOS",
    Image.LANCZOS,
)


def _flash_ok(message: str) -> None:
    """Registra un mensaje de éxito compatible con la UI actual."""
    flash(message, "success")


def _safe_internal_redirect(target: str | None, fallback: str) -> str:
    """Acepta solo redirecciones internas
        relativas para evitar open redirect."""
    if not target:
        return fallback

    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not target.startswith("/"):
        return fallback
    return target


def _pagination_items(current_page: int, total_pages: int) -> list[int | None]:
    """Construye una paginación compacta para la tabla principal."""
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    pages = {1, total_pages, current_page - 1, current_page, current_page + 1}
    pages = {page for page in pages if 1 <= page <= total_pages}
    ordered = sorted(pages)

    result: list[int | None] = []
    previous = None
    for page in ordered:
        if previous is not None and page - previous > 1:
            result.append(None)
        result.append(page)
        previous = page
    return result


def _load_zone_or_404(parcel_id: int) -> dict:
    """Recupera una zona o lanza 404 si no existe."""
    detail = get_zone_detail(parcel_id)
    if detail is None:
        abort(404)
    return detail


def _fetch_photo_bytes(photo: dict) -> bytes:
    """Obtiene los bytes de una tesela,
        priorizando el fichero local persistido."""
    local_image_path = get_storage_abspath(photo.get("ruta_foto"))
    if local_image_path and os.path.exists(local_image_path):
        with open(local_image_path, "rb") as image_file:
            return image_file.read()

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
    return _visor_fetch_tile_bytes(
        source,
        bbox3857,
        int(photo["width"]),
        int(photo["height"]),
    )


def _fetch_photo_traces(photo: dict) -> dict:
    """Recupera el JSON de trazas persistido para una tesela."""
    traces_path = get_storage_abspath(photo.get("ruta_trazas"))
    if not traces_path:
        raise FileNotFoundError(_("No hay trazas calculadas todavía."))

    if not os.path.exists(traces_path):
        raise FileNotFoundError(
            _(
                "Archivo de trazas no encontrado. "
                "Vuelve a calcularlas."
            )
        )

    try:
        with open(traces_path, "r", encoding="utf-8") as traces_file:
            return json.load(traces_file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            _(
                "Archivo de trazas corrupto o inválido. "
                "Vuelve a calcularlas."
            )
        ) from exc


def _render_photo_traces_overlay_png(
    photo: dict,
    image_bytes: bytes | None = None,
    traces: dict | None = None,
) -> bytes:
    """Genera una PNG con las trazas pintadas sobre la tesela."""
    if image_bytes is None:
        image_bytes = _fetch_photo_bytes(photo)
    if traces is None:
        traces = _fetch_photo_traces(photo)

    xs = traces.get("xs", [])
    ys = traces.get("ys", [])

    with Image.open(io.BytesIO(image_bytes)) as image:
        overlay = image.convert("RGB")

    pixels = overlay.load()
    width, height = overlay.size

    for x, y in zip(xs, ys):
        px = int(x)
        py = int(y)
        if 0 <= px < width and 0 <= py < height:
            pixels[px, py] = (255, 0, 0)

    buffer = io.BytesIO()
    overlay.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def _build_photo_download_zip(photo: dict) -> tuple[bytes, str]:
    """Construye el ZIP descargable de una tesela con sus artefactos."""
    image_bytes = _fetch_photo_bytes(photo)
    traces = _fetch_photo_traces(photo)
    overlay_png = _render_photo_traces_overlay_png(
        photo,
        image_bytes=image_bytes,
        traces=traces,
    )

    filename_root, extension = os.path.splitext(photo["filename"])
    zip_suffix = _("resultados")
    zip_name = f"{filename_root}_{zip_suffix}.zip"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(
        zip_buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            f"input/{filename_root}{extension}",
            image_bytes,
        )
        archive.writestr(
            f"output/{filename_root}_traces.json",
            json.dumps(traces, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            f"output/{filename_root}_traces.png",
            overlay_png,
        )

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), zip_name


def _zone_download_filename(detail: dict) -> str:
    """Construye un nombre de descarga legible para el ZIP de una zona."""
    base_name = secure_filename((detail.get("display_name") or "").strip())
    if not base_name:
        base_name = f"parcela_{detail['parcela_id']}"
    return f"{base_name}_tiles.zip"


def _build_zone_preview_bytes(detail: dict) -> bytes:
    """
    Construye una preview exacta de la zona a partir de sus teselas y luego la
    reduce proporcionalmente para que quepa dentro de 1024x640.

    No recorta ni deforma la imagen final: solo la escala manteniendo la
    relación de aspecto, por lo que el área representada sigue siendo
    exactamente la seleccionada por el usuario.
    """
    photos = detail.get("photos") or []
    if not photos:
        raise RuntimeError(_("La zona no contiene teselas."))

    col_widths: dict[int, int] = {}
    row_heights: dict[int, int] = {}

    for photo in photos:
        col_index = int(photo["col_index"])
        row_index = int(photo["row_index"])
        col_widths[col_index] = max(
            col_widths.get(col_index, 0),
            int(photo["width"]),
        )
        row_heights[row_index] = max(
            row_heights.get(row_index, 0),
            int(photo["height"]),
        )

    col_offsets: dict[int, int] = {}
    row_offsets: dict[int, int] = {}

    current_x = 0
    for col_index in sorted(col_widths):
        col_offsets[col_index] = current_x
        current_x += col_widths[col_index]

    current_y = 0
    for row_index in sorted(row_heights):
        row_offsets[row_index] = current_y
        current_y += row_heights[row_index]

    total_width = max(1, current_x)
    total_height = max(1, current_y)

    canvas = Image.new("RGB", (total_width, total_height), (245, 245, 245))
    loaded_tiles = 0

    for photo in photos:
        try:
            image_bytes = _fetch_photo_bytes(photo)
            with Image.open(io.BytesIO(image_bytes)) as image:
                tile = image.convert("RGB")
                expected_size = (int(photo["width"]), int(photo["height"]))

                if tile.size != expected_size:
                    tile = tile.resize(expected_size, _PREVIEW_RESAMPLING)

                x = col_offsets[int(photo["col_index"])]
                y = row_offsets[int(photo["row_index"])]
                canvas.paste(tile, (x, y))
                loaded_tiles += 1
        except Exception:
            current_app.logger.warning(
                "No se ha podido cargar la tesela %s para la preview "
                "de la zona %s",
                photo.get("foto_id"),
                detail.get("parcela_id"),
                exc_info=True,
            )

    if loaded_tiles == 0:
        raise RuntimeError(_("No se ha podido cargar la preview de la zona."))

    preview = canvas.copy()
    preview.thumbnail(
        (COLLECTION_PREVIEW_MAX_WIDTH, COLLECTION_PREVIEW_MAX_HEIGHT),
        _PREVIEW_RESAMPLING,
    )

    buffer = io.BytesIO()
    preview.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer.getvalue()


def register_collection_routes(bp) -> None:
    """Registra las rutas HTTP de la nueva colección de imágenes."""

    @bp.route("/coleccion", methods=["GET"])
    def collection():
        """Renderiza el listado persistente de zonas generadas."""
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1

        try:
            per_page = int(request.args.get("per_page", 10))
        except ValueError:
            per_page = 10

        if per_page not in COLLECTION_PER_PAGE_OPTIONS:
            per_page = 10

        search = request.args.get("q", "").strip()
        listing = list_zones(page=page, per_page=per_page, search=search)

        return render_template(
            "collection.html",
            listing=listing,
            pagination_items=_pagination_items(
                listing["page"],
                listing["total_pages"],
            ),
            per_page_options=COLLECTION_PER_PAGE_OPTIONS,
            current_query=request.full_path.rstrip(
                "?") or url_for("trazas.collection"),
        )

    @bp.route("/coleccion/status", methods=["GET"])
    def collection_status():
        """Devuelve el estado resumido de varias zonas para polling ligero."""
        raw_ids = request.args.get("ids", "").strip()
        parcel_ids = []

        for chunk in raw_ids.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                parcel_id = int(chunk)
            except ValueError:
                continue
            if parcel_id > 0 and parcel_id not in parcel_ids:
                parcel_ids.append(parcel_id)

        return jsonify(
            {
                "zones": list_zone_status_summaries(parcel_ids),
            }
        )

    @bp.route("/coleccion/<int:parcel_id>/status", methods=["GET"])
    def collection_zone_status(parcel_id: int):
        """Devuelve el estado completo de una zona y sus fotos."""
        status_payload = get_zone_live_status(parcel_id)
        if status_payload is None:
            return jsonify({"error": _("La zona solicitada no existe.")}), 404
        return jsonify(status_payload)

    @bp.route("/coleccion/<int:parcel_id>/preview", methods=["GET"])
    def collection_preview(parcel_id: int):
        """Devuelve una preview inline exacta de la zona completa."""
        detail = _load_zone_or_404(parcel_id)
        preview_path = get_zone_preview_abspath(parcel_id)

        if os.path.exists(preview_path):
            return send_file(
                preview_path,
                mimetype="image/jpeg",
                as_attachment=False,
                download_name=f"parcela_{parcel_id}_preview.jpg",
            )

        try:
            image_bytes = _build_zone_preview_bytes(detail)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception:
            current_app.logger.exception(
                "No se ha podido construir la preview de la zona %s",
                parcel_id,
            )
            return (
                jsonify(
                    {
                        "error": _(
                            "No se ha podido cargar la preview de la zona."
                        )
                    }
                ),
                502,
            )

        try:
            preview_path = save_zone_preview_bytes(parcel_id, image_bytes)
        except OSError:
            current_app.logger.exception(
                "No se ha podido persistir la preview de la zona %s",
                parcel_id,
            )
            return send_file(
                io.BytesIO(image_bytes),
                mimetype="image/jpeg",
                as_attachment=False,
                download_name=f"parcela_{parcel_id}_preview.jpg",
            )

        return send_file(
            preview_path,
            mimetype="image/jpeg",
            as_attachment=False,
            download_name=f"parcela_{parcel_id}_preview.jpg",
        )

    @bp.route("/coleccion/<int:parcel_id>/galeria", methods=["GET"])
    def collection_gallery(parcel_id: int):
        """Muestra una galería mínima de teselas asociadas a una zona."""
        detail = _load_zone_or_404(parcel_id)
        return render_template("collection_gallery.html", zone=detail)

    @bp.route("/coleccion/<int:parcel_id>/download-zip", methods=["GET"])
    def collection_download_zip(parcel_id: int):
        """Genera un ZIP descargable a partir de las teselas persistidas."""
        detail = _load_zone_or_404(parcel_id)
        if not detail["photos"]:
            abort(404)

        zip_buffer = io.BytesIO()
        log: dict[str, list] = {"downloaded": [], "failed": []}

        with zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for photo in detail["photos"]:
                try:
                    image_bytes = _fetch_photo_bytes(photo)
                    filename_root, extension = os.path.splitext(
                        photo["filename"])

                    archive.writestr(
                        f"input/{filename_root}{extension}",
                        image_bytes,
                    )

                    if photo.get("ruta_trazas"):
                        traces = _fetch_photo_traces(photo)
                        overlay_png = _render_photo_traces_overlay_png(
                            photo,
                            image_bytes=image_bytes,
                            traces=traces,
                        )
                        archive.writestr(
                            f"output/{filename_root}_traces.json",
                            json.dumps(
                                traces,
                                ensure_ascii=False,
                                indent=2,
                            ).encode("utf-8"),
                        )
                        archive.writestr(
                            f"output/{filename_root}_traces.png",
                            overlay_png,
                        )

                    log["downloaded"].append(photo["filename"])
                except Exception as exc:  # pragma: no cover
                    log["failed"].append(
                        {
                            "tile": photo["tile_id"],
                            "error": str(exc),
                        }
                    )

            archive.writestr(
                "log.json",
                json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8"),
            )

        zip_buffer.seek(0)
        zip_name = _zone_download_filename(detail)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    @bp.route("/coleccion/<int:parcel_id>/rename", methods=["POST"])
    def collection_rename(parcel_id: int):
        """Actualiza el nombre visible de una colección."""
        _load_zone_or_404(parcel_id)
        raw_name = request.form.get("name", "")

        try:
            update_zone_name(parcel_id, raw_name)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            if raw_name.strip():
                _flash_ok(
                    _("El nombre de la colección se "
                        "ha actualizado correctamente.")
                )
            else:
                _flash_ok(_("La colección ha recuperado "
                            "su nombre por defecto."))

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for("trazas.collection"),
        )
        return redirect(redirect_to)

    @bp.route("/coleccion/<int:parcel_id>/delete", methods=["POST"])
    def collection_delete(parcel_id: int):
        """Elimina permanentemente una zona de la colección."""
        try:
            deleted = delete_zone(parcel_id)
        except ZoneDeleteError as exc:
            current_app.logger.exception(
                "Error al eliminar la zona %s de la colección.",
                parcel_id,
            )
            flash(str(exc), "error")
        else:
            if deleted:
                _flash_ok(_("La zona se ha eliminado correctamente."))
            else:
                flash(_("La zona solicitada no existe."), "error")

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for("trazas.collection"),
        )
        return redirect(redirect_to)

    @bp.route("/coleccion/<int:parcel_id>/retry-pending-failed",
              methods=["POST"])
    def collection_zone_retry_pending_failed(parcel_id: int):
        """Recalcula solo las teselas pendientes o con error de una zona."""
        detail = _load_zone_or_404(parcel_id)
        photos = detail.get("photos") or []

        if not zone_retry_is_enabled(photos):
            if (
                detail.get("tile_count")
                and detail.get("completed_tiles") == detail.get("tile_count")
            ):
                flash(
                    _("Todas las teselas ya tienen las trazas calculadas."),
                    "info",
                )
            else:
                flash(
                    _(
                        "La recalculación masiva estará disponible cuando "
                        "existan teselas pendientes con al menos 2 minutos "
                        "de antigüedad o teselas con error."
                    ),
                    "warning",
                )
        else:
            retried_count = retry_zone_pending_and_failed(parcel_id)
            if retried_count > 0:
                _flash_ok(
                    _(
                        "Se han marcado %(count)s teselas pendientes o con "
                        "error para recalcular las trazas.",
                        count=retried_count,
                    )
                )
            else:
                flash(
                    _("No hay teselas pendientes o con "
                        "error para recalcular."),
                    "info",
                )

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for("trazas.collection_gallery", parcel_id=parcel_id),
        )
        return redirect(redirect_to)

    @bp.route("/coleccion/fotos/<int:photo_id>/retry", methods=["POST"])
    def collection_photo_retry(photo_id: int):
        """Marca una tesela para recalcular sus trazas."""
        photo = get_photo(photo_id)
        if photo is None:
            abort(404)

        if not photo_retry_is_enabled(photo):
            flash(
                _(
                    "La recalculación estará disponible 2 "
                    "minutos después de crear la tesela."
                ),
                "warning",
            )
        else:
            retry_photo(photo_id)
            _flash_ok(_("La tesela se ha marcado para recalcular las trazas."))

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for(
                "trazas.collection_gallery",
                parcel_id=photo["parcela_id"],
            ),
        )
        return redirect(redirect_to)

    @bp.route("/coleccion/fotos/<int:photo_id>/image", methods=["GET"])
    def collection_photo_image(photo_id: int):
        """Sirve una tesela inline para la galería sin forzar descarga."""
        photo = get_photo(photo_id)
        if photo is None:
            abort(404)

        try:
            image_bytes = _fetch_photo_bytes(photo)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/jpeg",
            as_attachment=False,
            download_name=photo["filename"],
        )

    @bp.route("/coleccion/fotos/<int:photo_id>/traces", methods=["GET"])
    def collection_photo_traces(photo_id: int):
        """Devuelve el JSON de trazas asociado a una tesela concreta."""
        photo = get_photo(photo_id)
        if photo is None:
            abort(404)

        try:
            traces = _fetch_photo_traces(photo)
        except FileNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 500

        return jsonify(traces)

    @bp.route("/coleccion/fotos/<int:photo_id>/download", methods=["GET"])
    def collection_photo_download(photo_id: int):
        """Descarga una tesela concreta o sus resultados si ya existen."""
        photo = get_photo(photo_id)
        if photo is None:
            abort(404)

        if photo.get("ruta_trazas"):
            try:
                zip_bytes, zip_name = _build_photo_download_zip(photo)
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 502
            except (FileNotFoundError, ValueError) as exc:
                current_app.logger.warning(
                    "No se han podido preparar los resultados de la foto %s",
                    photo_id,
                    exc_info=True,
                )
                return jsonify({"error": str(exc)}), 409

            return send_file(
                io.BytesIO(zip_bytes),
                mimetype="application/zip",
                as_attachment=True,
                download_name=zip_name,
            )

        try:
            image_bytes = _fetch_photo_bytes(photo)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name=photo["filename"],
        )
