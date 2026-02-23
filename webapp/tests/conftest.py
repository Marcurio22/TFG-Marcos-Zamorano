"""
==============================================================================
Archivo: conftest.py
Autor: Marcos Zamorano Lasso
Descripción:
Configura pytest para el proyecto. Añade el paquete trazasytrazadas
al sys.path, crea app de test y cliente de test.
==============================================================================
"""

import os
import sys
import tempfile
import pytest

# Añadir carpeta raíz webapp al sys.path.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from trazasytrazadas import create_app

@pytest.fixture
def app():
    """Crea una app Flask aislada por test run con carpetas temporales."""
    tmpdir = tempfile.TemporaryDirectory()
    upload = os.path.join(tmpdir.name, "uploads")
    output = os.path.join(tmpdir.name, "outputs")
    models = os.path.join(tmpdir.name, "models")

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "UPLOAD_FOLDER": upload,
            "OUTPUT_FOLDER": output,
            "SEG_MODELS_DIR": models,
            "SEG_USE_GPU": False,
            "SEG_MODEL_TEMPLATE": "data.8x(100imgs)_miou_method.unet_tu-mambaout_base_wide_rw_lr.9e-05_epochs.60_fold.{fold}",
            "SEG_N_FOLDS": 1,
        }
    )

    yield app
    tmpdir.cleanup()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def mock_compute_traces(monkeypatch):
    """Parcha trazasytrazadas.traces.compute_traces para no depender de ML real.

    Uso:
        mock_compute_traces()  -> devuelve trazas deterministas.
        mock_compute_traces(result={...})
        mock_compute_traces(exc=FileNotFoundError("..."))
    """
    from trazasytrazadas import traces as traces_module

    def _apply(result=None, exc: Exception | None = None):
        if exc is not None:
            def _raise(_image_path: str):
                raise exc
            monkeypatch.setattr(traces_module, "compute_traces", _raise)
            return None

        if result is None:
            result = {"xs": [1, 2, 3], "ys": [4, 5, 6]}

        monkeypatch.setattr(traces_module, "compute_traces", lambda _image_path: result)
        return result

    return _apply