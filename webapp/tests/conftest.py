"""
==============================================================================
Configura pytest para el proyecto. Añade el paquete trazasytrazadas
al sys.path, crea la app de test y expone fixtures comunes.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

import os
import sys
import tempfile

import pytest

from trazasytrazadas.db import db

# Añadir la carpeta raíz de webapp al sys.path antes de importar el paquete.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


@pytest.fixture
def app():
    """Crea una app Flask aislada con carpetas temporales."""
    from trazasytrazadas import create_app

    tmpdir = tempfile.TemporaryDirectory()
    upload = os.path.join(tmpdir.name, "uploads")
    output = os.path.join(tmpdir.name, "outputs")
    models = os.path.join(tmpdir.name, "models")
    database = os.path.join(tmpdir.name, "trazasytrazadas.sqlite")
    collection_storage = os.path.join(tmpdir.name, "collection")

    model_template = (
        "data.8x(100imgs)_miou_method.unet_tu-mambaout_base_wide_rw_lr"
        ".9e-05_epochs.60_fold.{fold}"
    )

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "UPLOAD_FOLDER": upload,
            "OUTPUT_FOLDER": output,
            "SEG_MODELS_DIR": models,
            "DATABASE": database,
            "COLLECTION_STORAGE_ROOT": collection_storage,
            "TRACE_WORKER_POLL_SECONDS": 0.01,
            "TRACE_WORKER_BATCH_SIZE": 1,
            "TRACE_WORKER_STALE_SECONDS": 60,
            "AUTO_START_TRACE_WORKER": False,
            "SEG_USE_GPU": False,
            "SEG_MODEL_TEMPLATE": model_template,
            "SEG_N_FOLDS": 1,
            "COLLECTION_PHOTO_RETRY_ENABLE_SECONDS": 0,
        }
    )

    yield app

    try:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
    finally:
        tmpdir.cleanup()


@pytest.fixture
def client(app):
    """Devuelve un cliente de pruebas de Flask."""
    return app.test_client()


@pytest.fixture
def mock_compute_traces(monkeypatch):
    """
    Parchea trazasytrazadas.traces.compute_traces para no depender
    del modelo real de segmentación.

    Uso:
        mock_compute_traces() -> trazas deterministas por defecto
        mock_compute_traces(result={...})
        mock_compute_traces(exc=Exception(...))
    """
    from trazasytrazadas import traces as traces_module

    def _apply(result=None, exc=None):
        if exc is not None:
            def _raise(_image_path):
                raise exc

            monkeypatch.setattr(traces_module, "compute_traces", _raise)
            return None

        if result is None:
            result = {"xs": [1, 2, 3], "ys": [4, 5, 6]}

        monkeypatch.setattr(
            traces_module,
            "compute_traces",
            lambda _image_path: result,
        )
        return result

    return _apply


@pytest.fixture
def force_login(app, client):
    """Autentica un usuario de pruebas en el cliente actual."""
    from werkzeug.security import generate_password_hash
    from trazasytrazadas.db import db
    from trazasytrazadas.models import Usuario

    def _force_login(
        username: str = "usuario_test",
        email: str = "usuario_test@example.com",
        role: str = "user",
    ) -> int:
        with app.app_context():
            user = Usuario(
                nombre_usuario=username,
                correo_electronico=email,
                telefono=None,
                contrasena=generate_password_hash("Password1!"),
                rol=role,
            )
            db.session.add(user)
            db.session.commit()
            user_id = int(user.usuario_id)

        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

        return user_id

    return _force_login
