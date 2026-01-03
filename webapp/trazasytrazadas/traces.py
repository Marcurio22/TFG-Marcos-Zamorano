"""
===============================================================================
Archivo: traces.py
Autor: Marcos Zamorano Lasso
Since: 19/11/2025
Descripción:
Contiene el blueprint principal de la aplicación, incluyendo las rutas:

- /               → Página principal
- /upload         → Insertar imagen
- /delete         → Borrar imagen
- /calculate      → Calcular trazas
- /traces    → Exponer JSON con las trazas calculadas

Funcionalidad:
    Este módulo gestiona todo el flujo del lado servidor. La aplicación 
    funciona siguiendo este proceso:
        1. Se sube una imagen original.
        2. El servidor calcula las trazas (puntos) usando la función
           compute_traces() y genera un JSON con coordenadas {xs, ys}.
        3. El JSON se sirve mediante /traces.
        4. El frontend (JavaScript) usa el JSON para dibujar las trazas en un
           <canvas> superpuesto sobre la imagen original.

Incluye utilidades para:
    - Validar archivos de imagen.
    - Calcular los puntos de prueba mediante el algoritmo de Bresenham.
    - Gestionar el estado de sesión.
    - Mostrar modales en la interfaz.
===============================================================================
"""

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
from PIL import Image #, ImageDraw

# -----------------------------------------------------------------------------
# Declaración del blueprint
# -----------------------------------------------------------------------------
# Este blueprint agrupa todas las rutas de la aplicación relacionadas con
# el flujo de imágenes y trazas.
bp = Blueprint("trazas", __name__)

# ---------------------------------------------------------------------------
# UTILIDADES INTERNAS
# ---------------------------------------------------------------------------

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


def bresenham_line(x0, y0, x1, y1):
    """
    Implementación del algoritmo de Bresenham para obtener todos los puntos
    enteros que forman una línea entre (x0, y0) y (x1, y1).

    Se usa para generar las diagonales en la imagen.
    Args:
        x0, y0 (int): coordenadas del punto inicial.
        x1, y1 (int): coordenadas del punto final.
    Returns:
        list[tuple[int, int]]: lista de puntos (x, y) a lo largo de la línea.
    """
    points = []

    # Diferencias absolutas.
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)

    # Dirección de avance.
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1

    # Error acumulado.
    err = dx + dy

    x, y = x0, y0
    while True:
        points.append((x, y))
        
        # Condición de parada: hemos llegado al punto final.
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        # Ajuste de error y coordenadas según el signo.
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy

    return points


def compute_traces(image_path: str) -> dict:
    """
    Calcula las trazas de prueba sobre una imagen.
    En esta versión inicial, las trazas consisten en:
        - Las 4 esquinas de la imagen.
        - El punto central.
        - Dos diagonales que cruzan la imagen pasando por el centro.
    Nota:
        En futuras versiones, aquí es donde se sustituirá esta lógica de prueba
        por el algoritmo real de detección de trazas de herbívoros.
    Args:
        image_path (str): ruta absoluta de la imagen original.
    Returns:
        dict: diccionario JSON con dos listas:
              {
                  "xs": [x0, x1, ...],
                  "ys": [y0, y1, ...],
              }
              donde (xs[i], ys[i]) son las coordenadas de cada píxel a pintar.
    """
    # Abrimos la imagen solo para obtener ancho y alto, ya que aquí no se modifica.
    with Image.open(image_path) as img:
        width, height = img.size

    points = []

    # 1) Esquinas: (0,0), (ancho-1, 0), (0, alto-1), (ancho-1, alto-1).
    points.extend(
        [
            (0, 0),
            (width - 1, 0),
            (0, height - 1),
            (width - 1, height - 1),
        ]
    )

    # 2) Punto central.
    cx = width // 2
    cy = height // 2
    points.append((cx, cy))

    # 3) Diagonal principal: esquina superior izq → esquina inferior dcha.
    points.extend(bresenham_line(0, 0, width - 1, height - 1))

    # 4) Diagonal secundaria: esquina inferior izq → esquina superior dcha.
    points.extend(bresenham_line(0, height - 1, width - 1, 0))

    # Eliminamos puntos duplicados manteniendo el orden original.
    seen = set()
    unique_points = []
    for p in points:
        if p not in seen:
            seen.add(p)
            unique_points.append(p)

    # Separamos en dos listas (xs, ys) para el JSON final.
    xs = [p[0] for p in unique_points]
    ys = [p[1] for p in unique_points]

    return {"xs": xs, "ys": ys}

def _set_error(message: str):
    """
    Guarda un mensaje de error en la sesión.
    Se mostrará en un modal en la siguiente petición al index.
    """
    session["error_message"] = message

# -----------------------------------------------------------------------------
# Rutas principales
# -----------------------------------------------------------------------------

#---------------- Ruta raíz ----------------------
@bp.route("/", methods=["GET"])
def index():
    """
    Página principal de la aplicación.

    Se encarga de:
        - Determinar qué imagen mostrar, si la original o la que contine las trazas.
        - Determinar el estado actual del flujo (sin imagen, imagen cargada,
          trazas calculadas, trazas dibujadas).
        - Mostrar modales de error o de "trazas calculadas".
    """
    # Nombre del fichero de la imagen original subida por el usuario.
    image_filename = session.get("image_filename")

    # Nombre del fichero JSON de trazas (se guarda en OUTPUT_FOLDER).
    traces_file = session.get("traces_file")

    # URL pública para la imagen original (usada en la plantilla).
    image_url = (
        url_for("trazas.uploaded_file", filename=image_filename)
        if image_filename
        else None
    )

    # Lógica de estado para la barra superior.
    if not image_filename:
        status = "no_image"
        status_message = (
            "Estado: ninguna imagen cargada. Inserta una imagen para empezar."
        )
    elif image_filename and not traces_file:
        status = "image_uploaded"
        status_message = "Estado: imagen cargada. Pulsa «Calcular trazas»."
    else:
        # Hay imagen y JSON de trazas calculado.
        status = "traces_calculated"
        status_message = (
            "Estado: trazas calculadas. Al cerrar el mensaje se dibujarán sobre la imagen."
        )

    # Recuperamos mensajes de error y flag de "trazas calculadas" para
    # mostrar modales. Usamos pop() para que se consuman una sola vez.
    error_message = session.pop("error_message", None)
    traces_modal = session.pop("traces_calculated", False)

    return render_template(
        "index.html",
        image_url=image_url,
        error_message=error_message,
        traces_calculated=traces_modal,
        status=status,
        status_message=status_message,
    )

#---------------- Ruta upload ----------------------
@bp.route("/upload", methods=["POST"])
def upload_image():
    """
    Ruta para insertar una nueva imagen en el sistema.

    Flujo:
        1. Valida que se ha enviado un archivo y que su extensión es válida.
        2. Guarda la imagen original en UPLOAD_FOLDER con un nombre único.
        3. Limpia el estado anterior (imagen previa, trazas previas, etc.).
        4. Redirige a la página principal.
    """
    # Comprobamos que el campo 'image' está presente en la petición.
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

    # Usamos secure_filename para evitar nombres de fichero peligrosos.
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)

    # Añadimos un sufijo UUID para garantizar unicidad.
    filename = f"{name}_{uuid.uuid4().hex}{ext}"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    # Limpieza de estado anterior (imagen, trazas, imagen trazada).
    old_image = session.pop("image_filename", None)
    old_traces_file = session.pop("traces_file", None)

    # Borramos físicamente los ficheros antiguos (si existen).
    for old, folder_key in [
        (old_image, "UPLOAD_FOLDER"),
        (old_traces_file, "OUTPUT_FOLDER"),
    ]:
        if old:
            try:
                os.remove(os.path.join(current_app.config[folder_key], old))
            except OSError:
                # Si no existe o no se puede borrar, ignoramos silenciosamente.
                pass

    # Guardamos en sesión el nombre de la nueva imagen.
    session["image_filename"] = filename

    return redirect(url_for("trazas.index"))

#---------------- Ruta delete ----------------------
@bp.route("/delete", methods=["POST"])
def delete_image():
    """
    Ruta para borrar la imagen actual y todo lo asociado.

    Si no hay imagen cargada, se genera un error.
    """
    # Comprueba que hay imagen cargada en sesión.
    image_filename = session.get("image_filename")

    if not image_filename:
        _set_error("No hay ninguna imagen cargada para borrar.")
        return redirect(url_for("trazas.index"))

    traces_file = session.get("traces_file")

    # Lista de (nombre_de_fichero, clave_de_carpeta) a eliminar.
    for old, folder_key in [
        (image_filename, "UPLOAD_FOLDER"),
        (traces_file, "OUTPUT_FOLDER"),
    ]:
        if old:
            try:
                os.remove(os.path.join(current_app.config[folder_key], old))
            except OSError:
                pass

    # Limpiamos las claves de sesión asociadas.
    session.pop("image_filename", None)
    session.pop("traces_file", None)

    return redirect(url_for("trazas.index"))

#---------------- Ruta calculate ----------------------
@bp.route("/calculate", methods=["POST"])
def calculate_traces():
    """
    Ruta para calcular el JSON de trazas de la imagen actual.

    Condiciones:
        - Debe existir una imagen subida; si no, se genera error.

    Efectos:
        - Calcula el diccionario {"xs": [...], "ys": [...]}.
        - Lo guarda en un fichero <nombre>_traces.json en OUTPUT_FOLDER.
        - Guarda en sesión el nombre de ese fichero ('traces_file').
        - Activa un flag en sesión para mostrar el modal de "trazas calculadas".
    """
    image_filename = session.get("image_filename")
    if not image_filename:
        _set_error("Primero debes insertar una imagen antes de calcular trazas.")
        return redirect(url_for("trazas.index"))

    image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], image_filename)

    # 1) Calculamos las trazas (diccionario con xs/ys).
    traces = compute_traces(image_path)

    # 2) Guardamos el JSON en un archivo dentro de OUTPUT_FOLDER.
    name, _ = os.path.splitext(image_filename)
    traces_filename = f"{name}_traces.json"
    traces_path = os.path.join(current_app.config["OUTPUT_FOLDER"], traces_filename)
    os.makedirs(current_app.config["OUTPUT_FOLDER"], exist_ok=True)

    with open(traces_path, "w", encoding="utf-8") as f:
        json.dump(traces, f)

    # 3) Guardamos en sesión solo el nombre del fichero JSON.
    session["traces_file"] = traces_filename

    # 4) Flag para mostrar modal "Trazas calculadas".
    session["traces_calculated"] = True

    return redirect(url_for("trazas.index"))

# -----------------------------------------------------------------------------
# Rutas auxiliares (servir imágenes y JSON)
# -----------------------------------------------------------------------------

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
    Endpoint para consultar el JSON de trazas actual.

    Útil para depuración y para verificar que el cálculo se realiza
    correctamente. El JSON se lee desde el fichero guardado en OUTPUT_FOLDER.
    """
    # Obtiene traces_file desde la sesión actual.
    traces_file = session.get("traces_file")

    # Si no, devuelve error.
    if not traces_file:
        return jsonify({"error": "No hay trazas calculadas todavía."}), 404

    # Busca archivo en output, si existe, devuelve traces.
    traces_path = os.path.join(current_app.config["OUTPUT_FOLDER"], traces_file)

    # Si no existe, lanza error.
    if not os.path.exists(traces_path):
        return (
            jsonify(
                {
                    "error": "Archivo de trazas no encontrado. Vuelve a calcularlas."
                }
            ),
            500,
        )

    # Abre archivo y lo convierte en formato JSON HTTP.
    with open(traces_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    return jsonify(traces)