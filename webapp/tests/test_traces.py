"""
Pruebas del flujo principal de cálculo y consulta de trazas.

Este módulo verifica que no se pueda calcular sin imagen previa y que el flujo
completo de subida, cálculo y consulta del endpoint /traces funcione con
un cálculo simulado.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io

from PIL import Image


def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    """Genera una imagen JPEG en memoria para usarla en las pruebas."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_calculate_requires_image(client):
    """Comprueba que /calculate falle si no hay imagen en sesión."""
    response = client.post("/calculate", follow_redirects=True)
    expected_msg = (
        b"Primero debes insertar una imagen antes de calcular trazas."
    )
    assert expected_msg in response.data


def test_full_traces_flow(client, mock_compute_traces):
    """
    Verifica el flujo completo: subida de imagen, cálculo simulado y consulta
    del JSON de trazas.
    """
    mock_compute_traces()

    data = {"image": (create_test_image_bytes(), "test.jpg")}
    resp_calc = client.post(
        "/upload_and_calculate",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_calc.status_code == 200

    # El pipeline debe dejar la imagen y el JSON registrados en sesión.
    with client.session_transaction() as sess:
        assert sess.get("image_filename")
        assert sess.get("traces_file")

    resp_json = client.get("/traces")
    assert resp_json.status_code == 200

    payload = resp_json.get_json()
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"xs", "ys"}
    assert isinstance(payload["xs"], list)
    assert isinstance(payload["ys"], list)
    assert len(payload["xs"]) == len(payload["ys"])
