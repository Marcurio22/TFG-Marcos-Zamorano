"""
Pruebas del flujo principal de cálculo y consulta de trazas.

Este módulo verifica:
- el estado inicial de la vista principal sin imagen,
- el estado de la vista cuando ya existe una imagen cargada,
- que no se pueda calcular sin imagen previa,
- y que el cálculo directo mediante /calculate funcione correctamente con un
  cálculo simulado.

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
    """Sube una imagen válida para preparar el estado en sesión."""
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_index_without_image_shows_empty_state(client):
    """Comprueba el estado inicial de la vista principal sin imagen."""
    response = client.get("/")
    assert response.status_code == 200

    assert "Sin imagen".encode("utf-8") in response.data
    assert (
        (
            "Estado: ninguna imagen cargada. "
            "Inserta una imagen para empezar."
        ).encode("utf-8")
    ) in response.data


def test_index_with_uploaded_image_shows_ready_state(client):
    """Comprueba el estado de la vista cuando hay imagen, pero no trazas."""
    upload_image(client)

    response = client.get("/")
    assert response.status_code == 200

    assert "Lista para calcular".encode("utf-8") in response.data
    assert (
        "Estado: imagen cargada. Pulsa «Calcular trazas».".encode("utf-8")
    ) in response.data
    assert b"/uploads/" in response.data


def test_calculate_requires_image(client):
    """Comprueba que /calculate falle si no hay imagen en sesión."""
    response = client.post("/calculate", follow_redirects=True)
    expected_msg = (
        b"Primero debes insertar una imagen antes de calcular trazas."
    )
    assert expected_msg in response.data


def test_calculate_success_stores_traces_and_updates_index(
    client, mock_compute_traces
):
    """
    Verifica que /calculate genere el JSON de trazas, lo registre en sesión y
    deje la vista principal en estado de trazas calculadas.
    """
    expected_traces = {"xs": [1, 2, 3], "ys": [4, 5, 6]}
    mock_compute_traces(result=expected_traces)

    upload_image(client)

    response = client.post("/calculate", follow_redirects=True)
    assert response.status_code == 200

    assert "Trazas calculadas".encode("utf-8") in response.data
    assert (
        "Estado: trazas calculadas. Se dibujarán automáticamente sobre la "
        "imagen.".encode("utf-8")
    ) in response.data
    assert b'"autoDrawTraces": true' in response.data

    with client.session_transaction() as sess:
        image_filename = sess.get("image_filename")
        traces_file = sess.get("traces_file")

    assert image_filename
    assert traces_file

    traces_path = os.path.join(
        client.application.config["OUTPUT_FOLDER"], traces_file
    )
    assert os.path.exists(traces_path)

    resp_json = client.get("/traces")
    assert resp_json.status_code == 200
    assert resp_json.get_json() == expected_traces
