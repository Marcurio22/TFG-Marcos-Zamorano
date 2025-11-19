import io
from PIL import Image


def create_test_image_bytes():
    img = Image.new("RGB", (10, 10), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_upload_image(client):
    data = {
        "image": (create_test_image_bytes(), "test.jpg"),
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")

    # Debe redirigir de vuelta al index
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_invalid_extension(client):
    data = {
        "image": (io.BytesIO(b"fake"), "test.txt"),
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data", follow_redirects=True)

    assert b"Formato de archivo no permitido" in response.data