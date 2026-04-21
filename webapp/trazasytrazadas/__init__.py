"""
===============================================================================
Inicialización y configuración de la aplicación Flask del paquete
trazasytrazadas.

Este módulo define la factoría create_app(), carga la configuración base,
prepara los directorios de trabajo en instance/, configura la
internacionalización con Flask-Babel y registra el blueprint principal.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

import os
from datetime import timedelta
from flask import Flask, request, session
from flask_babel import Babel, get_locale
from pathlib import Path

from . import auth, db, traces, trace_worker
from .admin import init_admin

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
    """
    Devuelve el idioma activo para la petición actual.
    El orden de resolución es:
    1. Parámetro de consulta lang.
    2. Valor almacenado en session["lang"].
    3. Cabecera Accept-Language del navegador.
    4. "es" como valor por defecto.
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
        test_config (dict | None): Configuración de prueba opcional que
            sobrescribe la configuración por defecto.

    Returns:
        Flask: Instancia de la aplicación ya configurada.
    """

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
        DATABASE=os.path.join(app.instance_path, "trazasytrazadas.sqlite"),
        LEGACY_PARCEL_OWNER_USERNAME="Vindi22",

        # ----- Configuración de almacenamiento y trazas en segundo plano -----
        COLLECTION_STORAGE_ROOT=os.path.join(app.instance_path, "collection"),
        TRACE_WORKER_POLL_SECONDS=2.0,
        TRACE_WORKER_BATCH_SIZE=1,
        AUTO_START_TRACE_WORKER=True,
        TRACE_WORKER_STALE_SECONDS=600,
        COLLECTION_PHOTO_RETRY_ENABLE_SECONDS=120,

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

    # Sesión: 24h máximo, sin refresco automático.
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False

    @app.before_request
    def _make_session_permanent():
        session.permanent = True

    # Configuración de tests.
    if test_config is not None:
        app.config.update(test_config)
    else:
        app.config.from_pyfile("config.py", silent=True)

    # Configuración de SQLAlchemy.
    database_path = Path(app.config["DATABASE"]).resolve()
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        f"sqlite:///{database_path.as_posix()}",
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    # Configuración de internacionalización.
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

    # Integración de extensiones.
    db.init_app(app)
    auth.init_app(app)
    trace_worker.init_app(app)

    with app.app_context():
        db.init_db()
        os.makedirs(app.config["COLLECTION_STORAGE_ROOT"], exist_ok=True)

    # Registrar blueprint principal.
    app.register_blueprint(traces.bp)

    # Asocia la URL raíz con el endpoint principal del blueprint.
    app.add_url_rule("/", endpoint="trazas.index")

    # Inicializa panel de administración.
    init_admin(app)

    return app
