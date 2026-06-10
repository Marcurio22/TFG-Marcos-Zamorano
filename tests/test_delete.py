"""Pruebas para la ruta /delete y la limpieza del estado asociado.

Autor: Marcos Zamorano Lasso
Versión: 1.0
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
    """Sube una imagen válida al endpoint de carga estándar."""
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_delete_requires_image(client):
    """Comprueba que el borrado exige una imagen cargada en sesión."""
    resp = client.post("/delete", follow_redirects=True)
    assert (
        "No hay ninguna imagen cargada para borrar.".encode("utf-8")
        in resp.data
    )


def test_delete_cleans_files_and_session(client, mock_compute_traces):
    # Sustituye el cálculo real para evitar depender de pesos de segmentación.
    """Comprueba que el borrado limpia archivos temporales y sesión."""
    mock_compute_traces()

    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post(
        "/upload_and_calculate",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    # Recupera los nombres persistidos en sesión y verifica que existen.
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

    client.post("/delete", follow_redirects=True)

    assert not os.path.exists(upload_path)
    assert not os.path.exists(traces_path)

    # La sesión debe quedar sin referencias a la imagen ni al JSON de trazas.
    with client.session_transaction() as sess:
        assert "image_filename" not in sess
        assert "traces_file" not in sess

    # Sin trazas en sesión, el endpoint vuelve a responder como no disponible.
    resp = client.get("/traces")
    assert resp.status_code == 404
