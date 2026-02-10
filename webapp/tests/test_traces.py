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

def upload_image(client):
    """Helper para subir automáticamente una imagen de prueba."""
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
    )

def test_calculate_requires_image(client):
    """Debe ser imposible calcular trazas sin haber subido una imagen."""
    response = client.post("/calculate", follow_redirects=True)
    assert b"Primero debes insertar una imagen antes de calcular trazas." in response.data

def test_full_traces_flow(client, mock_compute_traces):
    """Flujo completo esperado:
    1) Subir imagen.
    2) Calcular trazas (mock, sin ML real).
    3) Consultar /traces (JSON con xs/ys).
    """
    mock_compute_traces()

    upload_image(client)

    resp_calc = client.post("/calculate", follow_redirects=True)
    assert b"Las trazas de la imagen han sido calculadas correctamente." in resp_calc.data

    resp_json = client.get("/traces")
    assert resp_json.status_code == 200

    data = resp_json.get_json()
    assert isinstance(data, dict)
    assert set(data.keys()) == {"xs", "ys"}
    assert isinstance(data["xs"], list)
    assert isinstance(data["ys"], list)
    assert len(data["xs"]) == len(data["ys"])