"""
Pruebas de manejo de errores para la ruta /calculate.

Este módulo verifica que la aplicación responde correctamente cuando el cálculo
de trazas falla por ausencia de recursos o por errores inesperados durante la
ejecución.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io

from PIL import Image


def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    """Genera una imagen JPEG en memoria para usarla en las pruebas."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def upload_image(client):
    """Sube una imagen válida para preparar el estado previo al cálculo."""
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_calculate_handles_filenotfounderror(client, mock_compute_traces):
    """Verifica que el comportamiento esperado gestiona el caso previsto."""
    upload_image(client)

    mock_compute_traces(exc=FileNotFoundError("Missing weights"))

    resp = client.post("/calculate", follow_redirects=True)
    assert "Missing weights".encode("utf-8") in resp.data


def test_calculate_handles_generic_exception(client, mock_compute_traces):
    """Verifica que el comportamiento esperado gestiona el caso previsto."""
    upload_image(client)

    mock_compute_traces(exc=RuntimeError("Boom"))

    resp = client.post("/calculate", follow_redirects=True)
    assert "Error ejecutando segmentación:".encode("utf-8") in resp.data
    assert "Boom".encode("utf-8") in resp.data
