import io
from PIL import Image


def create_test_image_bytes():
    img = Image.new("RGB", (20, 20), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def upload_image(client):
    data = {"image": (create_test_image_bytes(), "test.jpg")}
    client.post("/upload", data=data, content_type="multipart/form-data")


def test_calculate_requires_image(client):
    resp = client.post("/calculate", follow_redirects=True)
    assert b"Primero debes insertar una imagen" in resp.data


def test_draw_requires_traces(client):
    upload_image(client)
    resp = client.post("/draw", follow_redirects=True)
    assert b"Debes calcular las trazas antes de dibujarlas." in resp.data


def test_full_traces_flow(client):
    upload_image(client)

    # calcular
    resp_calc = client.post("/calculate", follow_redirects=True)
    assert b"Las trazas de la imagen han sido calculadas." in resp_calc.data

    # ver JSON
    resp_json = client.get("/traces.json")
    assert resp_json.status_code == 200
    data = resp_json.get_json()
    assert set(data.keys()) == {"xs", "ys"}
    assert len(data["xs"]) == len(data["ys"])

    # dibujar
    resp_draw = client.post("/draw", follow_redirects=True)
    assert resp_draw.status_code == 200