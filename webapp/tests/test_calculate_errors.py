"""
Tests de manejo de errores en /calculate.
(Falta cabecera)
"""

import io
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


def test_calculate_handles_filenotfounderror(client, mock_compute_traces):
    upload_image(client)

    mock_compute_traces(exc=FileNotFoundError("Missing weights"))

    resp = client.post("/calculate", follow_redirects=True)
    assert "Missing weights".encode("utf-8") in resp.data


def test_calculate_handles_generic_exception(client, mock_compute_traces):
    upload_image(client)

    mock_compute_traces(exc=RuntimeError("Boom"))

    resp = client.post("/calculate", follow_redirects=True)
    assert "Error ejecutando segmentación:".encode("utf-8") in resp.data
    assert "Boom".encode("utf-8") in resp.data
