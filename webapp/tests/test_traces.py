"""
===============================================================================
 Archivo: test_traces.py
 Proyecto: Trazas y Trazadas (tests)
 Autor: Marcos Zamorano Lasso
 Since: 19/11/2025
 Descripción:
     Tests que cubren el flujo de cálculo y dibujo de trazas:

       - No se puede calcular trazas sin imagen.
       - No se puede dibujar trazas sin haberlas calculado antes.
       - Flujo completo:
           subir imagen → calcular trazas → consultar JSON → dibujar trazas.
===============================================================================
"""

import io
from PIL import Image

# ---------------------------------------------------------------------------
# Utilidades para los tests
# ---------------------------------------------------------------------------

def create_test_image_bytes(size=(20, 20)) -> io.BytesIO:
    """
    Crea una pequeña imagen JPEG en memoria para usar en los tests.

    Args:
        size (tuple[int, int]): tamaño de la imagen (ancho, alto).

    Returns:
        io.BytesIO: buffer con la imagen en formato JPEG.
    """
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf

def upload_image(client):
    """
    Helper para subir automáticamente una imagen de prueba usando el cliente
    de tests de Flask.

    Args:
        client: fixture 'client' proporcionada por conftest.py.
    """
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post(
        "/upload",
        data=data,
        content_type="multipart/form-data",
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_calculate_requires_image(client):
    """
    Debe ser imposible calcular trazas si todavía no se ha subido ninguna imagen.

    Esperamos que aparezca un mensaje de error adecuado en la respuesta.
    """
    response = client.post("/calculate", follow_redirects=True)
    assert b"Primero debes insertar una imagen" in response.data

def test_draw_requires_traces(client):
    """
    Debe ser imposible dibujar trazas si no se han calculado previamente.

    Flujo:
      1. Subimos una imagen.
      2. Intentamos dibujar trazas directamente (sin calcular).
      3. Debe aparecer el mensaje de error correspondiente.
    """
    upload_image(client)  # Tenemos imagen, pero aún no hay JSON de trazas.

    response = client.post("/draw", follow_redirects=True)

    assert b"Debes calcular las trazas antes de dibujarlas." in response.data


def test_full_traces_flow(client):
    """
    Flujo completo esperado de uso:

      1. Subir una imagen.
      2. Calcular trazas.
      3. Consultar el JSON de trazas en /traces.json.
      4. Dibujar las trazas sobre la imagen.

    Verificamos que:
      - El modal de 'trazas calculadas' se muestra.
      - /traces.json devuelve un JSON con listas 'xs' y 'ys' de igual longitud.
      - La petición para dibujar trazas finaliza correctamente (200).
    """
    # 1) Subimos una imagen de prueba.
    upload_image(client)

    # 2) Calculamos trazas.
    resp_calc = client.post("/calculate", follow_redirects=True)
    assert b"Las trazas de la imagen han sido calculadas." in resp_calc.data

    # 3) Consultamos el JSON de trazas.
    resp_json = client.get("/traces.json")
    assert resp_json.status_code == 200

    data = resp_json.get_json()
    assert isinstance(data, dict)
    assert set(data.keys()) == {"xs", "ys"}
    assert len(data["xs"]) == len(data["ys"])

    # 4) Dibujamos las trazas sobre la imagen.
    resp_draw = client.post("/draw", follow_redirects=True)
    assert resp_draw.status_code == 200