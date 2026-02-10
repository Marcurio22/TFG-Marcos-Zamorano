"""
Tests para la ruta /delete (borrado de imagen y trazas asociadas).
(Falta cabecera buena)
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

def test_delete_requires_image(client):
    resp = client.post("/delete", follow_redirects=True)
    assert "No hay ninguna imagen cargada para borrar.".encode("utf-8") in resp.data

def test_delete_cleans_files_and_session(client, mock_compute_traces):
    # Patch ML para poder calcular sin pesos reales
    mock_compute_traces()

    # 1) Upload + calculate para generar image + JSON
    upload_image(client)
    client.post("/calculate", follow_redirects=True)

    # 2) Capturamos nombres en sesión y comprobamos que existen en disco
    with client.session_transaction() as sess:
        image_filename = sess.get("image_filename")
        traces_file = sess.get("traces_file")

    assert image_filename
    assert traces_file

    upload_path = os.path.join(client.application.config["UPLOAD_FOLDER"], image_filename)
    traces_path = os.path.join(client.application.config["OUTPUT_FOLDER"], traces_file)

    assert os.path.exists(upload_path)
    assert os.path.exists(traces_path)

    # 3) Delete
    client.post("/delete", follow_redirects=True)

    assert not os.path.exists(upload_path)
    assert not os.path.exists(traces_path)

    # 4) Sesión limpia
    with client.session_transaction() as sess:
        assert "image_filename" not in sess
        assert "traces_file" not in sess

    # 5) /traces vuelve a 404
    resp = client.get("/traces")
    assert resp.status_code == 404