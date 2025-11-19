import os
import uuid
import json

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
)
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw

bp = Blueprint("trazas", __name__)


# ---------- utilidades internas ----------

def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def bresenham_line(x0, y0, x1, y1):
    points = []

    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy

    return points


def compute_traces(image_path: str) -> dict:
    """Calcula las trazas de test (esquinas, centro y diagonales)."""

    with Image.open(image_path) as img:
        width, height = img.size

    points = []

    # 4 esquinas
    points.extend(
        [
            (0, 0),
            (width - 1, 0),
            (0, height - 1),
            (width - 1, height - 1),
        ]
    )

    # punto medio
    cx = width // 2
    cy = height // 2
    points.append((cx, cy))

    # diagonales pasando por el centro
    points.extend(bresenham_line(0, 0, width - 1, height - 1))
    points.extend(bresenham_line(0, height - 1, width - 1, 0))

    # eliminar duplicados manteniendo orden
    seen = set()
    unique_points = []
    for p in points:
        if p not in seen:
            seen.add(p)
            unique_points.append(p)

    xs = [p[0] for p in unique_points]
    ys = [p[1] for p in unique_points]

    return {"xs": xs, "ys": ys}


def draw_traces_on_image(image_path: str, traces: dict) -> str:
    """Dibuja los puntos de 'traces' sobre la imagen y guarda una nueva."""
    base_name = os.path.basename(image_path)
    name, ext = os.path.splitext(base_name)
    output_filename = f"{name}_trazas{ext}"

    output_folder = current_app.config["OUTPUT_FOLDER"]
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, output_filename)

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    points = list(zip(traces["xs"], traces["ys"]))
    draw.point(points, fill=(255, 0, 0))

    img.save(output_path)

    return output_filename


def _set_error(message: str):
    session["error_message"] = message


# ---------- vistas ----------

@bp.route("/", methods=["GET"])
def index():
    image_filename = session.get("image_filename")
    traced_filename = session.get("traced_filename")
    traces_file = session.get("traces_file")  # guardamos nombre de fichero

    image_url = None
    traced_image_url = None

    if image_filename:
        image_url = url_for("trazas.uploaded_file", filename=image_filename)
    if traced_filename:
        traced_image_url = url_for("trazas.traced_file", filename=traced_filename)

    # Estado para la interfaz
    if not image_filename:
        status = "no_image"
        status_message = "Estado: ninguna imagen cargada. Inserta una imagen para empezar."
    elif image_filename and not traces_file:
        status = "image_uploaded"
        status_message = "Estado: imagen cargada. Pulsa «Calcular trazas»."
    elif traces_file and not traced_filename:
        status = "traces_calculated"
        status_message = "Estado: trazas calculadas. Pulsa «Dibujar trazas» para verlas."
    else:
        status = "traces_drawn"
        status_message = "Estado: trazas dibujadas sobre la imagen."

    error_message = session.pop("error_message", None)
    traces_modal = session.pop("traces_calculated", False)

    return render_template(
        "index.html",
        image_url=image_url,
        traced_image_url=traced_image_url,
        error_message=error_message,
        traces_calculated=traces_modal,
        status=status,
        status_message=status_message,
    )


@bp.route("/upload", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        _set_error("No se ha enviado ningún archivo.")
        return redirect(url_for("trazas.index"))

    file = request.files["image"]

    if file.filename == "":
        _set_error("No se ha seleccionado ningún archivo.")
        return redirect(url_for("trazas.index"))

    if not allowed_file(file.filename):
        _set_error("Formato de archivo no permitido. Usa .jpg, .jpeg o .png.")
        return redirect(url_for("trazas.index"))

    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{uuid.uuid4().hex}{ext}"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    # limpiar estado anterior
    old_image = session.pop("image_filename", None)
    old_traced = session.pop("traced_filename", None)
    old_traces_file = session.pop("traces_file", None)

    # borrar ficheros antiguos (revisar con Álvar)
    for old, folder_key in [
        (old_image, "UPLOAD_FOLDER"),
        (old_traced, "OUTPUT_FOLDER"),
        (old_traces_file, "OUTPUT_FOLDER"),
    ]:
        if old:
            try:
                os.remove(os.path.join(current_app.config[folder_key], old))
            except OSError:
                pass

    session["image_filename"] = filename

    return redirect(url_for("trazas.index"))


@bp.route("/delete", methods=["POST"])
def delete_image():
    image_filename = session.get("image_filename")
    if not image_filename:
        _set_error("No hay ninguna imagen cargada para borrar.")
        return redirect(url_for("trazas.index"))

    traced_filename = session.get("traced_filename")
    traces_file = session.get("traces_file")

    for old, folder_key in [
        (image_filename, "UPLOAD_FOLDER"),
        (traced_filename, "OUTPUT_FOLDER"),
        (traces_file, "OUTPUT_FOLDER"),
    ]:
        if old:
            try:
                os.remove(os.path.join(current_app.config[folder_key], old))
            except OSError:
                pass

    session.pop("image_filename", None)
    session.pop("traced_filename", None)
    session.pop("traces_file", None)

    return redirect(url_for("trazas.index"))


@bp.route("/calculate", methods=["POST"])
def calculate_traces():
    image_filename = session.get("image_filename")
    if not image_filename:
        _set_error("Primero debes insertar una imagen antes de calcular trazas.")
        return redirect(url_for("trazas.index"))

    image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], image_filename)

    traces = compute_traces(image_path)

    # Guardar JSON en fichero en disco
    name, _ = os.path.splitext(image_filename)
    traces_filename = f"{name}_traces.json"
    traces_path = os.path.join(current_app.config["OUTPUT_FOLDER"], traces_filename)
    os.makedirs(current_app.config["OUTPUT_FOLDER"], exist_ok=True)
    with open(traces_path, "w", encoding="utf-8") as f:
        json.dump(traces, f)

    session["traces_file"] = traces_filename
    session["traced_filename"] = None
    session["traces_calculated"] = True

    return redirect(url_for("trazas.index"))


@bp.route("/draw", methods=["POST"])
def draw_traces():
    image_filename = session.get("image_filename")
    if not image_filename:
        _set_error("No hay imagen sobre la que dibujar trazas.")
        return redirect(url_for("trazas.index"))

    traces_file = session.get("traces_file")
    if not traces_file:
        _set_error("Debes calcular las trazas antes de dibujarlas.")
        return redirect(url_for("trazas.index"))

    traces_path = os.path.join(current_app.config["OUTPUT_FOLDER"], traces_file)
    if not os.path.exists(traces_path):
        _set_error("No se ha encontrado el archivo de trazas. Vuelve a calcularlas.")
        session.pop("traces_file", None)
        return redirect(url_for("trazas.index"))

    with open(traces_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], image_filename)
    traced_filename = draw_traces_on_image(image_path, traces)

    session["traced_filename"] = traced_filename

    return redirect(url_for("trazas.index"))


# ---------- endpoints auxiliares ----------

@bp.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/outputs/<filename>")
def traced_file(filename):
    return send_from_directory(current_app.config["OUTPUT_FOLDER"], filename)


@bp.route("/traces.json")
def traces_json():
    """Devuelve el JSON de trazas desde el fichero."""
    traces_file = session.get("traces_file")
    if not traces_file:
        return jsonify({"error": "No hay trazas calculadas todavía."}), 404

    traces_path = os.path.join(current_app.config["OUTPUT_FOLDER"], traces_file)
    if not os.path.exists(traces_path):
        return jsonify({"error": "Archivo de trazas no encontrado. Vuelve a calcularlas."}), 500

    with open(traces_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    return jsonify(traces)