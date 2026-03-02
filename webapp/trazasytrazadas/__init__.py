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
from datetime import timedelta
from flask import Flask, request, session
from flask_babel import Babel, get_locale

from . import traces

# Babel (i18n)
babel = Babel()

LANGUAGES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "it": "Italiano",
    "de": "Deutsch",
}


def select_locale():
    """Selecciona idioma por request en este orden:
    1) Querystring ?lang=xx
    2) session["lang"]
    3) Accept-Language header del navegador
    4) fallback a 'es'
    """
    lang = request.args.get("lang")
    if lang in LANGUAGES:
        session["lang"] = lang
        return lang

    lang = session.get("lang")
    if lang in LANGUAGES:
        return lang

    return request.accept_languages.best_match(LANGUAGES.keys()) or "es"


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
    seg_model_template = (
        "data.8x(100imgs)_miou_method.unet_tu-mambaout_base_wide_rw_"
        "lr.9e-05_epochs.60_fold.{fold}"
    )

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
        SEG_MODEL_TEMPLATE=seg_model_template,

        # Número de folds/modelos que intentará cargar.
        SEG_N_FOLDS=10,

        # Usar GPU si existe.
        SEG_USE_GPU=True,
    )

    # Sesión: 24h máximo (sin extensión por actividad)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False

    @app.before_request
    def _make_session_permanent():
        session.permanent = True

    # Configuración de tests, en caso de ser proporcionada.
    if test_config is not None:
        app.config.update(test_config)
    else:
        app.config.from_pyfile("config.py", silent=True)

    # ------------------ Configuración i18n (Flask-Babel) ------------------
    app.config.setdefault("BABEL_DEFAULT_LOCALE", "es")
    app.config.setdefault("BABEL_DEFAULT_TIMEZONE", "Europe/Madrid")

    babel.init_app(app, locale_selector=select_locale)

    @app.context_processor
    def _inject_i18n():
        loc = get_locale()
        current_lang = getattr(loc, "language", str(loc))
        return {"LANGUAGES": LANGUAGES, "current_lang": current_lang}

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
