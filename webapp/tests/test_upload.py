"""
Pruebas relacionadas con la subida de imágenes.

Este módulo cubre la subida correcta de archivos válidos y distintos casos de
error asociados a peticiones incompletas o extensiones no permitidas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io

from PIL import Image


def create_test_image_bytes(size=(10, 10)) -> io.BytesIO:
    """
    Genera una imagen JPEG en memoria para usarla en las pruebas.

    Args:
        size (tuple[int, int]): Tamaño de la imagen en
            formato (ancho, alto).

    Returns:
        io.BytesIO: Buffer listo para enviarse como archivo en una petición.
    """
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_upload_image_ok(client):
    """Comprueba que una subida válida redirige a la vista principal."""
    data = {
        "image": (create_test_image_bytes(), "test.jpg"),
    }

    response = client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_invalid_extension(client):
    """
    Comprueba que la aplicación rechaza archivos con una extensión no válida.
    """
    data = {
        "image": (io.BytesIO(b"contenido-falso"), "test.txt"),
    }

    response = client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"Formato de archivo no permitido" in response.data


def test_upload_missing_image_field(client):
    """Comprueba el error cuando no se envía el campo image."""
    response = client.post(
        "/upload",
        data={},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"alert-error" in response.data


def test_upload_empty_filename(client):
    """Comprueba el error cuando el campo image llega sin nombre."""
    data = {"image": (io.BytesIO(b"contenido"), "")}
    response = client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "No se ha seleccionado ningún archivo.".encode(
        "utf-8"
    ) in response.data
