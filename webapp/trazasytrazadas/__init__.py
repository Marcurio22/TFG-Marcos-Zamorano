"""
===============================================================================
Archivo: __init__.py
Autor: Marcos Zamorano Lasso
Since: 19/11/2025
Descripción:
Archivo principal del paquete trazasytrazadas. Define la application factory
siguiendo el tutorial oficial de Flask. Se encarga de:

    - Crear la instancia principal de la aplicación Flask.
    - Cargar la configuración por defecto y, opcionalmente, una configuración
      específica de tests o desde instance/config.py.
    - Configurar las rutas y carpetas base de trabajo:
          • UPLOAD_FOLDER  → almacenamiento de las imágenes originales
                             subidas por el usuario.
          • OUTPUT_FOLDER  → almacenamiento de los resultados de cálculo,
                             concretamente los ficheros JSON con las trazas.
    - Asegurar la existencia de la carpeta instance/ y sus subcarpetas.
    - Registrar el blueprint principal del proyecto (traces.bp).
    - Asociar la ruta raíz (/) con la vista trazas.index.

Notas:
    • La lógica de cálculo de trazas y la gestión del JSON se encuentran en
      trazasytrazadas/traces.py.
    • La aplicación utiliza instance_relative_config=True para separar código
      fuente y datos generados.
===============================================================================
"""

import os
from flask import Flask

from . import traces

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
        SECRET_KEY="dev",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        ALLOWED_EXTENSIONS={"png", "jpg", "jpeg"},
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        OUTPUT_FOLDER=os.path.join(app.instance_path, "outputs"),

        # ------------------ Configuración ML ------------------
        # Carpeta donde van los pesos por fold.
        SEG_MODELS_DIR=os.path.join(app.root_path, "model"),

        # Template de pesos por fold.
        SEG_MODEL_TEMPLATE="data.8x(100imgs)_miou_method.unet_tu-mambaout_base_wide_rw_lr.9e-05_epochs.60_fold.{fold}",

        # Número de folds/modelos que intentará cargar.
        SEG_N_FOLDS=10,

        # Encoder usado al entrenar (debe coincidir).
        SEG_ENCODER_NAME="tu-mambaout_base_wide_rw",

        # Usar GPU si existe (si no hay GPU, caerá a CPU automáticamente).
        SEG_USE_GPU=True,
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
    os.makedirs(app.config["SEG_MODELS_DIR"], exist_ok=True)

    # Registrar blueprint principal.
    app.register_blueprint(traces.bp)

    # Ruta raíz: redirigimos a trazas.index.
    app.add_url_rule("/", endpoint="trazas.index")

    return app