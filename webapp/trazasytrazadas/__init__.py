import os
from flask import Flask

def create_app(test_config=None):
    """Application factory siguiendo el patrón del tutorial de Flask."""

    # Config fuera del paquete
    app = Flask(__name__, instance_relative_config=True)

    # Configuración por defecto
    app.config.from_mapping(
        SECRET_KEY="dev",  # NOTA: Devo cambiar esto en producción
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB
        ALLOWED_EXTENSIONS={"png", "jpg", "jpeg"},
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        OUTPUT_FOLDER=os.path.join(app.instance_path, "outputs"),
    )

    # Config extra
    if test_config is not None:
        app.config.update(test_config)
    else:
        # Si existe instance/config.py, lo cargamos
        app.config.from_pyfile("config.py", silent=True)

    # Asegurarse de que existen las carpetas necesarias
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["OUTPUT_FOLDER"], exist_ok=True)

    # Registrar blueprint principal
    from . import traces
    app.register_blueprint(traces.bp)

    # Hacer que "/" vaya al index del blueprint
    app.add_url_rule("/", endpoint="trazas.index")

    return app