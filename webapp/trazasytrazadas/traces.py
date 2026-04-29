"""
Blueprint principal y utilidades del flujo de imágenes y trazas.

Este módulo define las rutas encargadas de la carga de imágenes, el cálculo
de trazas, la consulta del JSON generado y la descarga de resultados. También
incluye funciones auxiliares para validar archivos, gestionar el estado de
sesión y preparar los artefactos asociados al procesamiento.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import os
import uuid
import json
import re

import io
import zipfile
import numpy as np

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    jsonify,
    flash,
    send_file,
    abort,
)
from flask_babel import gettext as _
from werkzeug.utils import secure_filename
from .segmentation_inference import compute_traces_from_segmentation
from .visor import register_visor_routes
from .collection import register_collection_routes
from .auth import register_auth_routes
from PIL import Image

# Blueprint principal de la aplicación.
bp = Blueprint("trazas", __name__)

# Registro de rutas auxiliares del visor.
register_visor_routes(bp)
register_collection_routes(bp)
register_auth_routes(bp)

# Utilidades internas.


def allowed_file(filename: str) -> bool:
    """
    Comprueba si el fichero tiene una extensión permitida.
    Args:
        filename (str): nombre de fichero proporcionado por el usuario.
    Returns:
        bool: True si la extensión es válida, False en caso contrario.
    """
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def compute_traces(image_path: str) -> dict:
    """
    Calcula las trazas asociadas a una imagen mediante el pipeline de
    segmentación configurado en la aplicación.

    Esta función delega el procesamiento en
    compute_traces_from_segmentation() y devuelve un diccionario con el
    formato esperado por el frontend:

        {"xs": [...], "ys": [...]}

    donde cada par (xs[i], ys[i]) representa un píxel a dibujar sobre la
    imagen.
    """
    cfg = current_app.config

    return compute_traces_from_segmentation(
        image_path=image_path,
        models_dir=cfg["SEG_MODELS_DIR"],
        model_template=cfg["SEG_MODEL_TEMPLATE"],
        n_folds=cfg["SEG_N_FOLDS"],
        use_gpu=cfg["SEG_USE_GPU"],
    )


def _set_error(message: str):
    """Registra un mensaje de error para su visualización en la interfaz."""
    flash(message, "error")


def _flash_ok(message: str):
    """Mensajes de éxito (UI: alert-success)."""
    flash(message, "success")


def _flash_info(message: str):
    """Mensajes informativos (UI: alert-info)."""
    flash(message, "info")


def _cleanup_previous_state(
    old_image: str | None, old_traces_file: str | None
) -> None:
    """Elimina de disco los artefactos previos si existen."""
    for old, folder_key in [
        (old_image, "UPLOAD_FOLDER"),
        (old_traces_file, "OUTPUT_FOLDER"),
    ]:
        if not old:
            continue
        try:
            os.remove(os.path.join(current_app.config[folder_key], old))
        except OSError:
            # Si no existe o no se puede borrar, se ignora.
            pass


def _save_uploaded_image(file) -> str:
    """Guarda una imagen subida y devuelve el filename final con UUID."""
    # Usa secure_filename para evitar nombres de fichero peligrosos.
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{uuid.uuid4().hex}{ext}"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    return filename


def _handle_upload_file_or_error(file) -> bool:
    """
    Valida el archivo recibido, limpia el estado previo y guarda la imagen.

    Returns:
        bool: True si la imagen se procesa correctamente; False si se
        produce un error y ya se ha notificado mediante flash.
    """
    if not file or not file.filename:
        _set_error(_("No se ha seleccionado ningún archivo."))
        return False

    max_bytes = current_app.config.get("IMAGE_UPLOAD_MAX_CONTENT_LENGTH")
    if max_bytes and request.content_length:
        try:
            max_bytes = int(max_bytes)
        except (TypeError, ValueError):
            max_bytes = 0
        if max_bytes > 0 and request.content_length > max_bytes:
            _set_error(_("La imagen supera el tamaño máximo permitido."))
            return False

    if not allowed_file(file.filename):
        _set_error(
            _("Formato de archivo no permitido. Usa .jpg, .jpeg o .png.")
        )
        return False

    # Al cargar una nueva imagen se invalidan los artefactos asociados a la
    # sesión anterior.
    old_image = session.pop("image_filename", None)
    old_traces_file = session.pop("traces_file", None)
    _cleanup_previous_state(old_image, old_traces_file)

    filename = _save_uploaded_image(file)
    session["image_filename"] = filename
    return True


def _calculate_and_store_traces(image_filename: str) -> str:
    """Calcula y persiste el JSON de trazas; devuelve el nombre del JSON."""
    image_path = os.path.join(
        current_app.config["UPLOAD_FOLDER"], image_filename)

    traces = compute_traces(image_path)

    name, _ = os.path.splitext(image_filename)
    traces_filename = f"{name}_traces.json"
    traces_path = os.path.join(
        current_app.config["OUTPUT_FOLDER"], traces_filename)
    os.makedirs(current_app.config["OUTPUT_FOLDER"], exist_ok=True)
    with open(traces_path, "w", encoding="utf-8") as f:
        json.dump(traces, f)
    return traces_filename


def _render_traces_overlay_png(image_path: str, traces_path: str) -> bytes:
    """Genera una PNG con las trazas pintadas en rojo sobre la imagen."""
    with open(traces_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    xs = traces.get("xs", [])
    ys = traces.get("ys", [])

    with Image.open(image_path) as im:
        im = im.convert("RGB")
        arr = np.array(im).copy()

    h, w = arr.shape[:2]
    for x, y in zip(xs, ys):
        x = int(x)
        y = int(y)
        if 0 <= x < w and 0 <= y < h:
            arr[y, x] = (255, 0, 0)

    out = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


_UUID_SUFFIX_RE = re.compile(r"^(?P<base>.+)_[0-9a-f]{32}$", re.IGNORECASE)


def _strip_uuid_from_saved_filename(saved_filename: str) -> str:
    """
    Convierte:
      image_1_cace55ae3fa943d596cdd5fb695b9d0d.png -> image_1
      test.jpg -> test
    """
    stem, _ext = os.path.splitext(saved_filename)
    m = _UUID_SUFFIX_RE.match(stem)
    return m.group("base") if m else stem

# Rutas principales.

# ---------------- Ruta raíz ----------------------


@bp.route("/", methods=["GET"])
def index():
    """
    Renderiza la página principal y prepara el estado actual de la vista.

    Determina la imagen disponible, comprueba si existen trazas calculadas y
    construye el contexto que utiliza la plantilla para representar el estado
    del flujo de trabajo.
    """
    # Nombre del fichero de la imagen original subida por el usuario.
    image_filename = session.get("image_filename")

    # Nombre del fichero JSON de trazas.
    traces_file = session.get("traces_file")

    # URL pública para la imagen original.
    image_url = (
        url_for("trazas.uploaded_file", filename=image_filename)
        if image_filename
        else None
    )

    # Lógica de estado para la barra superior.
    if not image_filename:
        status = "no_image"
        status_message = _(
            "Estado: ninguna imagen cargada. Inserta una imagen para empezar."
        )
    elif image_filename and not traces_file:
        status = "image_uploaded"
        status_message = _("Estado: imagen cargada. Pulsa «Calcular trazas».")
    else:
        # Hay imagen y JSON de trazas calculado.
        status = "traces_calculated"
        status_message = _(
            "Estado: trazas calculadas. Se dibujarán automáticamente "
            "sobre la imagen."
        )

    # Si hay trazas calculadas, el frontend dibuja automáticamente.
    auto_draw_traces = bool(traces_file)

    return render_template(
        "index.html",
        image_url=image_url,
        auto_draw_traces=auto_draw_traces,
        status=status,
        status_message=status_message,
    )

# ---------------- Ruta upload ----------------------


@bp.route("/upload", methods=["POST"])
def upload_image():
    """
    Ruta para insertar una nueva imagen en el sistema.

    Flujo:
        1. Valida que se ha enviado un archivo y que su extensión es válida.
        2. Guarda la imagen original en UPLOAD_FOLDER con un nombre único.
        3. Limpia el estado anterior.
        4. Redirige a la página principal.
    """
    file = request.files.get("image")
    if not _handle_upload_file_or_error(file):
        return redirect(url_for("trazas.index"))

    _flash_ok(_("Imagen cargada correctamente."))
    return redirect(url_for("trazas.index"))

# ---------------- Ruta delete ----------------------


@bp.route("/delete", methods=["POST"])
def delete_image():
    """
    Ruta para borrar la imagen actual y todo lo asociado.

    Si no hay imagen cargada, se genera un error.
    """
    # Comprueba que hay imagen cargada en sesión.
    image_filename = session.get("image_filename")

    if not image_filename:
        _set_error(_("No hay ninguna imagen cargada para borrar."))
        return redirect(url_for("trazas.index"))

    traces_file = session.get("traces_file")

    _cleanup_previous_state(image_filename, traces_file)

    # Limpiamos las claves de sesión asociadas.
    session.pop("image_filename", None)
    session.pop("traces_file", None)

    _flash_ok(_("Imagen borrada correctamente."))

    return redirect(url_for("trazas.index"))

# ---------------- Ruta calculate ----------------------


@bp.route("/calculate", methods=["POST"])
def calculate_traces():
    """
    Calcula y guarda el JSON de trazas para la imagen actual.

    Condiciones:
        - Debe existir una imagen subida; si no, se notifica un error.

    Efectos:
        - Calcula el diccionario {"xs": [...], "ys": [...]}.
        - Lo guarda en un fichero <nombre>_traces.json en
          OUTPUT_FOLDER.
        - Guarda en sesión el nombre de ese fichero en "traces_file".
    """
    image_filename = session.get("image_filename")
    if not image_filename:
        _set_error(
            _("Primero debes insertar una imagen antes de calcular trazas."))
        return redirect(url_for("trazas.index"))

    # 1) Calculamos y guardamos trazas.
    try:
        traces_filename = _calculate_and_store_traces(image_filename)
    except FileNotFoundError as e:
        _set_error(str(e))
        return redirect(url_for("trazas.index"))
    except Exception as e:
        current_app.logger.exception("Error ejecutando segmentación")
        _set_error(_("Error ejecutando segmentación: %(error)s", error=str(e)))
        return redirect(url_for("trazas.index"))

    # 2) Guardamos en sesión solo el nombre del fichero JSON.
    session["traces_file"] = traces_filename

    _flash_ok(_("Las trazas de la imagen han sido calculadas correctamente."))

    return redirect(url_for("trazas.index"))


# ---------------- Ruta upload + calculate ----------------------
@bp.route("/upload_and_calculate", methods=["POST"])
def upload_and_calculate():
    """
    Pipeline usado por el frontend:

    - Si viene un fichero en request.files['image'], lo guarda.
    - Si no viene fichero, usa la imagen ya presente en sesión.
    - En ambos casos calcula y persiste el JSON de trazas.
    """

    file = request.files.get("image")

    if file and file.filename:
        if not _handle_upload_file_or_error(file):
            return redirect(url_for("trazas.index"))

    return calculate_traces()

# ---------------- Ruta de descarga de resultados ----------------------


@bp.route("/download_results", methods=["GET"])
def download_results():
    """
    Genera un archivo ZIP en memoria con los resultados de la sesión actual.

    El ZIP incluye la imagen original, el JSON de trazas calculado y una
    imagen PNG con las trazas superpuestas.
    """
    image_filename = session.get("image_filename")
    traces_file = session.get("traces_file")

    if not image_filename or not traces_file:
        abort(404)

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    output_folder = current_app.config["OUTPUT_FOLDER"]

    image_path = os.path.join(upload_folder, image_filename)
    traces_path = os.path.join(output_folder, traces_file)

    if not os.path.exists(image_path) or not os.path.exists(traces_path):
        abort(404)

    # Se elimina el sufijo UUID para generar nombres de descarga más legibles.
    display_base = _strip_uuid_from_saved_filename(image_filename)
    _ext = os.path.splitext(image_filename)[1]

    # Sufijo traducido por idioma.
    zip_suffix = _("resultados")

    overlay_name = f"{display_base}_traces.png"
    zip_name = f"{display_base}_{zip_suffix}.zip"

    # El overlay se genera en memoria para incluirlo en el ZIP sin crear
    # archivos temporales adicionales en disco.
    overlay_png = _render_traces_overlay_png(image_path, traces_path)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(image_path, arcname=f"input/{display_base}{_ext}")
        z.write(traces_path, arcname=f"output/{display_base}_traces.json")
        z.writestr(f"output/{overlay_name}", overlay_png)

    zip_buf.seek(0)
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
    )

# Rutas auxiliares: servicio de imágenes y JSON.

# ----------- Ruta GET/uploads/<filename> ------------


@bp.route("/uploads/<filename>")
def uploaded_file(filename: str):
    """
    Sirve la imagen original subida por el usuario.
    """
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

# -------------------- Ruta traces -----------------------


@bp.route("/traces")
def traces_json():
    """
    Devuelve el JSON de trazas asociado a la sesión actual.

    Si no hay trazas calculadas o el fichero ya no existe en disco, responde
    con el error HTTP correspondiente.
    """
    traces_file = session.get("traces_file")

    if not traces_file:
        return jsonify({"error": _("No hay trazas calculadas todavía.")}), 404

    traces_path = os.path.join(
        current_app.config["OUTPUT_FOLDER"], traces_file)

    if not os.path.exists(traces_path):
        return (
            jsonify(
                {
                    "error": _(
                        "Archivo de trazas no encontrado. "
                        "Vuelve a calcularlas."
                    )
                }
            ),
            500,
        )

    try:
        with open(traces_path, "r", encoding="utf-8") as f:
            traces = json.load(f)
    except json.JSONDecodeError:
        # Caso 2: fichero corrupto o inválido.
        return (
            jsonify(
                {
                    "error": _(
                        "Archivo de trazas corrupto o inválido. "
                        "Vuelve a calcularlas."
                    ),
                    "code": "TRACES_JSON_CORRUPT",
                }
            ),
            500,
        )

    return jsonify(traces)
