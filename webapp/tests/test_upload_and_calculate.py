"""
Tests para el pipeline /upload_and_calculate.

Este endpoint permite al frontend:
  - Previsualizar una imagen (sin backend)
  - Y, al pulsar "Calcular trazas", subir + calcular en una sola petición.
"""

import io
import os
from PIL import Image


def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def upload_image(client):
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_pipeline_upload_and_calculate_with_file(client, mock_compute_traces):
    mock_compute_traces()

    data = {"image": (create_test_image_bytes(), "test.jpg")}
    resp = client.post(
        "/upload_and_calculate",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # Verifica sesión y artefactos en disco.
    with client.session_transaction() as sess:
        image_filename = sess.get("image_filename")
        traces_file = sess.get("traces_file")

    assert image_filename
    assert traces_file

    upload_path = os.path.join(client.application.config["UPLOAD_FOLDER"], image_filename)
    traces_path = os.path.join(client.application.config["OUTPUT_FOLDER"], traces_file)

    assert os.path.exists(upload_path)
    assert os.path.exists(traces_path)

    # Y además, /traces debe devolver JSON válido
    resp_json = client.get("/traces")
    assert resp_json.status_code == 200
    payload = resp_json.get_json()
    assert set(payload.keys()) == {"xs", "ys"}


def test_pipeline_calculate_without_file_uses_session_image(client, mock_compute_traces):
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
    resp = client.post("/upload_and_calculate", follow_redirects=True)
    assert "Primero debes insertar una imagen antes de calcular trazas.".encode("utf-8") in resp.data