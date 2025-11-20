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
    tmpdir = tempfile.TemporaryDirectory()
    upload = os.path.join(tmpdir.name, "uploads")
    output = os.path.join(tmpdir.name, "outputs")

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "UPLOAD_FOLDER": upload,
            "OUTPUT_FOLDER": output,
        }
    )

    yield app
    tmpdir.cleanup()


@pytest.fixture
def client(app):
    return app.test_client()