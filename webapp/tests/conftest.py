import os
import sys
import tempfile

# --- Mete la carpeta webapp en sys.path ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


import pytest
from trazasytrazadas import create_app


@pytest.fixture
def app():
    # Crear carpetas temporales para uploads y outputs
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