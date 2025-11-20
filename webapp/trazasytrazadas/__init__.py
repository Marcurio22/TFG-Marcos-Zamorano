"""
===============================================================================
Archivo: __init__.py
Autor: Marcos Zamorano Lasso
Since: 19/11/2025
Descripción:
Archivo principal del paquete trazasytrazadas. Define la application
factory siguiendo el tutorial oficial de Flask. Configura rutas, carpetas
de subida, carpeta de salida para imágenes con trazas y registra el
blueprint principal del proyecto.
===============================================================================
"""

import os
from flask import Flask

def create_app(test_config=None):
    """
    Crea y configura la aplicación Flask.

    Args:
    test_config (dict | None): configuración de test opcional.

    Returns:
    Flask: instancia de la aplicación.
    """

    # La aplicación usará instance_relative_config para permitir almacenar
    # archivos fuera del código fuente.
    app = Flask(__name__, instance_relative_config=True)

    # Configuración por defecto.
    app.config.from_mapping(
        SECRET_KEY="dev",  # NOTA: Debo cambiar esto en producción.
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB.
        ALLOWED_EXTENSIONS={"png", "jpg", "jpeg"},
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        OUTPUT_FOLDER=os.path.join(app.instance_path, "outputs"),
    )

    # Configuración de tests, en caso de ser proporcionada.
    if test_config is not None:
        app.config.update(test_config)
    else:
        # Si existe instance/config.py, lo cargamos.
        app.config.from_pyfile("config.py", silent=True)

    # Crear las carpetas necesarias.
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

    # Registrar blueprint principal.
    from . import traces
    app.register_blueprint(traces.bp)

    # Ruta raíz: redirigimos a trazas.index.
    app.add_url_rule("/", endpoint="trazas.index")

    return app