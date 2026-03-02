"""
Pruebas del endpoint /upload_and_calculate.

Este módulo cubre el comportamiento del pipeline combinado que permite usar una
imagen enviada en la misma petición o reutilizar la imagen ya almacenada en
sesión para calcular trazas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io
import os

from PIL import Image


def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    """Genera una imagen JPEG en memoria para usarla en las pruebas."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def upload_image(client):
    """Sube una imagen válida para dejar el estado preparado en sesión."""
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_pipeline_upload_and_calculate_with_file(client, mock_compute_traces):
    """Verifica el flujo combinado cuando la petición incluye una imagen."""
    mock_compute_traces()

    data = {"image": (create_test_image_bytes(), "test.jpg")}
    resp = client.post(
        "/upload_and_calculate",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # Comprueba que la sesión y los archivos generados quedan disponibles.
    with client.session_transaction() as sess:
        image_filename = sess.get("image_filename")
        traces_file = sess.get("traces_file")

    assert image_filename
    assert traces_file

    upload_path = os.path.join(
        client.application.config["UPLOAD_FOLDER"], image_filename
    )
    traces_path = os.path.join(
        client.application.config["OUTPUT_FOLDER"], traces_file
    )

    assert os.path.exists(upload_path)
    assert os.path.exists(traces_path)

    # El endpoint de consulta debe exponer el JSON generado.
    resp_json = client.get("/traces")
    assert resp_json.status_code == 200
    payload = resp_json.get_json()
    assert set(payload.keys()) == {"xs", "ys"}


def test_pipeline_calculate_without_file_uses_session_image(
    client, mock_compute_traces
):
    """Verifica que el endpoint reutiliza la imagen guardada en sesión."""
    mock_compute_traces()
    upload_image(client)

    resp = client.post("/upload_and_calculate", follow_redirects=True)
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("image_filename")
        assert sess.get("traces_file")

    resp_json = client.get("/traces")
    assert resp_json.status_code == 200
    payload = resp_json.get_json()
    assert set(payload.keys()) == {"xs", "ys"}


def test_pipeline_requires_image_if_no_file_and_no_session(client):
    """Debe fallar si no hay fichero enviado ni imagen previa en sesión."""
    resp = client.post("/upload_and_calculate", follow_redirects=True)
    error_msg = (
        "Primero debes insertar una imagen antes de calcular trazas."
    )
    assert error_msg.encode("utf-8") in resp.data
