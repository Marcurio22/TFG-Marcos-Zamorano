"""
===============================================================================
 Archivo: test_traces.py
 Proyecto: Trazas y Trazadas (tests)
 Autor: Marcos Zamorano Lasso
 Since: 19/11/2025
 Descripción:
     Tests que cubren el flujo de cálculo y consulta de trazas:

       - No se puede calcular trazas sin imagen.
       - Flujo completo: subir → calcular (mock) → consultar /traces.
===============================================================================
"""

import io
from PIL import Image


def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    """Crea una pequeña imagen JPEG en memoria para usar en los tests."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_calculate_requires_image(client):
    """Debe ser imposible calcular trazas sin haber subido una imagen."""
    response = client.post("/calculate", follow_redirects=True)
    expected_msg = (
        b"Primero debes insertar una imagen antes de calcular trazas."
    )
    assert expected_msg in response.data


def test_full_traces_flow(client, mock_compute_traces):
    """Flujo completo esperado:
    1) Subir imagen.
    2) Calcular trazas (mock, sin ML real).
    3) Consultar /traces (JSON con xs/ys).
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

    # Verificamos que el pipeline ha dejado estado en sesión
    with client.session_transaction() as sess:
        assert sess.get("image_filename")
        assert sess.get("traces_file")

    # /traces debe devolver JSON válido
    resp_json = client.get("/traces")
    assert resp_json.status_code == 200

    payload = resp_json.get_json()
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"xs", "ys"}
    assert isinstance(payload["xs"], list)
    assert isinstance(payload["ys"], list)
    assert len(payload["xs"]) == len(payload["ys"])
