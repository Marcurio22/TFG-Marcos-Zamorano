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


def test_pipeline_replaces_image_and_cleans_previous_files(
    client, mock_compute_traces
):
    """
    Verifica que al subir una nueva imagen en el pipeline se limpia el estado
    anterior y no se mezclan resultados.
    """
    first_traces = {"xs": [10, 11], "ys": [20, 21]}
    mock_compute_traces(result=first_traces)

    data_1 = {"image": (create_test_image_bytes(), "first.jpg")}
    resp_1 = client.post(
        "/upload_and_calculate",
        data=data_1,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_1.status_code == 200

    with client.session_transaction() as sess:
        first_image = sess.get("image_filename")
        first_traces_file = sess.get("traces_file")

    assert first_image
    assert first_traces_file

    upload_dir = client.application.config["UPLOAD_FOLDER"]
    out_dir = client.application.config["OUTPUT_FOLDER"]

    first_image_path = os.path.join(upload_dir, first_image)
    first_traces_path = os.path.join(out_dir, first_traces_file)

    assert os.path.exists(first_image_path)
    assert os.path.exists(first_traces_path)

    second_traces = {"xs": [1, 2, 3], "ys": [4, 5, 6]}
    mock_compute_traces(result=second_traces)

    data_2 = {"image": (create_test_image_bytes(), "second.jpg")}
    resp_2 = client.post(
        "/upload_and_calculate",
        data=data_2,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_2.status_code == 200

    with client.session_transaction() as sess:
        second_image = sess.get("image_filename")
        second_traces_file = sess.get("traces_file")

    assert second_image
    assert second_traces_file
    assert second_image != first_image
    assert second_traces_file != first_traces_file

    second_image_path = os.path.join(upload_dir, second_image)
    second_traces_path = os.path.join(out_dir, second_traces_file)

    assert os.path.exists(second_image_path)
    assert os.path.exists(second_traces_path)

    # El estado anterior debe limpiarse al reemplazar la imagen.
    assert not os.path.exists(first_image_path)
    assert not os.path.exists(first_traces_path)

    resp_json = client.get("/traces")
    assert resp_json.status_code == 200
    assert resp_json.get_json() == second_traces
