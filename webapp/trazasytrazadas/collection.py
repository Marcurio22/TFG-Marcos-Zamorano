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

import os
import io
import json
import zipfile
from urllib.parse import urlparse

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_babel import gettext as _

from .collection_store import (
    delete_zone,
    get_photo,
    get_storage_abspath,
    get_zone_detail,
    get_zone_live_status,
    list_zone_status_summaries,
    list_zones,
    retry_photo,
)
from .visor import _visor_fetch_tile_bytes, _visor_source_by_id

COLLECTION_PER_PAGE_OPTIONS = (10, 25, 50)


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
        """Devuelve una preview inline basada en
            la primera tesela de la zona."""
        detail = _load_zone_or_404(parcel_id)
        if not detail["photos"]:
            return jsonify({"error": _("La zona no contiene teselas.")}), 404

        try:
            image_bytes = _fetch_photo_bytes(detail["photos"][0])
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

        return send_file(
            io.BytesIO(image_bytes),
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
                    archive.writestr(photo["filename"],
                                     _fetch_photo_bytes(photo))
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
        zip_name = f"coleccion_parcela_{parcel_id}_tiles.zip"
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    @bp.route("/coleccion/<int:parcel_id>/delete", methods=["POST"])
    def collection_delete(parcel_id: int):
        """Elimina permanentemente una zona de la colección."""
        deleted = delete_zone(parcel_id)
        if deleted:
            _flash_ok(_("La zona se ha eliminado correctamente."))
        else:
            flash(_("La zona solicitada no existe."), "error")

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for("trazas.collection"),
        )
        return redirect(redirect_to)

    @bp.route("/coleccion/fotos/<int:photo_id>/retry", methods=["POST"])
    def collection_photo_retry(photo_id: int):
        """Marca una tesela para reintentar el cálculo de su traza."""
        photo = get_photo(photo_id)
        if photo is None:
            abort(404)

        if photo["estado"] == "completed":
            flash(_("La tesela ya está completada."), "info")
        else:
            retry_photo(photo_id)
            _flash_ok(_("La tesela se ha marcado para recalcular la traza."))

        redirect_to = _safe_internal_redirect(
            request.form.get("redirect_to"),
            url_for("trazas.collection_gallery",
                    parcel_id=photo["parcela_id"]),
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

    @bp.route("/coleccion/fotos/<int:photo_id>/download", methods=["GET"])
    def collection_photo_download(photo_id: int):
        """Descarga una tesela concreta persistida en la colección."""
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
            as_attachment=True,
            download_name=photo["filename"],
        )
