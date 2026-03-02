"""
===============================================================================
 Archivo: test_upload.py
 Autor: Marcos Zamorano Lasso
 Since: 189/11/2025
 Descripción:
     Tests relacionados con la subida de imágenes:

       - Subida correcta de una imagen válida (.jpg).
       - Rechazo de archivos con extensión inválida.
===============================================================================
"""

import io
from PIL import Image


def create_test_image_bytes(size=(10, 10)) -> io.BytesIO:
    """
    Crea una imagen pequeñita en memoria y la devuelve como BytesIO.

    Esto evita tener que leer archivos desde disco durante los tests.

    Args:
        size (tuple[int, int]): tamaño de la imagen (ancho, alto).

    Returns:
        io.BytesIO: buffer con contenido JPEG listo para enviar como fichero.
    """
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_upload_image_ok(client):
    """
    Comprueba que subir una imagen JPEG válida:
        - Devuelve una redirección (302).
        - Redirige a la página principal ('/').
    """
    data = {
        "image": (create_test_image_bytes(), "test.jpg"),
    }

    response = client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
    )

    # La vista redirige siempre al index tras procesar la subida.
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_invalid_extension(client):
    """
    Comprueba que si intentamos subir un archivo con extensión NO permitida,
    la aplicación muestra un mensaje de error.

    Se usa follow_redirects=True para obtener el HTML final del index
    después de la redirección y buscar el texto del error.
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

    # El mensaje de error se pinta en la plantilla cuando la extensión
    # no es válida.
    assert b"Formato de archivo no permitido" in response.data


def test_upload_missing_image_field(client):
    """Si no se envía el campo 'image' en request.files, debe mostrar error."""
    response = client.post(
        "/upload",
        data={},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert b"alert-error" in response.data


def test_upload_empty_filename(client):
    """Si se envía 'image' pero con filename vacío, debe mostrar error."""
    data = {"image": (io.BytesIO(b"contenido"), "")}
    response = client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "No se ha seleccionado ningún archivo.".encode(
        "utf-8") in response.data
