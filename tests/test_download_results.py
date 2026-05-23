"""
Pruebas para la ruta /download_results.

Este módulo verifica que la descarga de resultados:
- falle con 404 si no hay estado suficiente en sesión,
- falle con 404 si la sesión apunta a archivos inexistentes,
- y genere un ZIP válido con la imagen original, el JSON de trazas
  y el PNG de overlay cuando el flujo previo se ha completado.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import io
import json
import os
import zipfile

from PIL import Image


def create_test_image_bytes(size=(20, 20), image_format="PNG") -> io.BytesIO:
    """Genera una imagen en memoria para usarla en las pruebas."""
    img = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    img.save(buf, format=image_format)
    buf.seek(0)
    return buf


def test_download_results_returns_404_without_session_state(client):
    """Debe devolver 404 si no hay imagen ni trazas registradas en sesión."""
    resp = client.get("/download_results")
    assert resp.status_code == 404


def test_download_results_returns_404_when_files_are_missing(client):
    """Debe devolver 404 si la sesión apunta a archivos inexistentes."""
    with client.session_transaction() as sess:
        sess["image_filename"] = "missing_image.png"
        sess["traces_file"] = "missing_traces.json"

    resp = client.get("/download_results")
    assert resp.status_code == 404


def test_download_results_returns_expected_zip(client, mock_compute_traces):
    """Debe generar un ZIP válido con los tres artefactos esperados."""
    traces = {"xs": [1, 2], "ys": [3, 4]}
    mock_compute_traces(result=traces)

    data = {"image": (create_test_image_bytes(), "image_1.png")}
    resp_calc = client.post(
        "/upload_and_calculate",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_calc.status_code == 200

    resp = client.get("/download_results")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert ".zip" in disposition

    zip_buf = io.BytesIO(resp.data)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        names = set(zf.namelist())
        assert names == {
            "input/image_1.png",
            "output/image_1_traces.json",
            "output/image_1_traces.png",
        }

        traces_payload = json.loads(
            zf.read("output/image_1_traces.json").decode("utf-8")
        )
        assert traces_payload == traces

        overlay_png = zf.read("output/image_1_traces.png")
        assert overlay_png.startswith(b"\x89PNG\r\n\x1a\n")


def test_download_results_returns_404_when_image_missing_only(client):
    """Debe devolver 404 si falta la imagen,
    aunque exista el JSON de trazas."""
    out_dir = client.application.config["OUTPUT_FOLDER"]
    upload_dir = client.application.config["UPLOAD_FOLDER"]

    traces_name = "only_traces.json"
    traces_path = os.path.join(out_dir, traces_name)

    with open(traces_path, "w", encoding="utf-8") as f:
        json.dump({"xs": [1], "ys": [2]}, f)

    missing_image = "missing_only_image.png"
    missing_image_path = os.path.join(upload_dir, missing_image)
    if os.path.exists(missing_image_path):
        os.remove(missing_image_path)

    with client.session_transaction() as sess:
        sess["image_filename"] = missing_image
        sess["traces_file"] = traces_name

    resp = client.get("/download_results")
    assert resp.status_code == 404


def test_download_results_returns_404_when_traces_missing_only(client):
    """Debe devolver 404 si falta el JSON de trazas,
    aunque exista la imagen."""
    out_dir = client.application.config["OUTPUT_FOLDER"]
    upload_dir = client.application.config["UPLOAD_FOLDER"]

    image_name = "only_image.png"
    image_path = os.path.join(upload_dir, image_name)
    with open(image_path, "wb") as f:
        f.write(create_test_image_bytes(image_format="PNG").read())

    missing_traces = "missing_only_traces.json"
    missing_traces_path = os.path.join(out_dir, missing_traces)
    if os.path.exists(missing_traces_path):
        os.remove(missing_traces_path)

    with client.session_transaction() as sess:
        sess["image_filename"] = image_name
        sess["traces_file"] = missing_traces

    resp = client.get("/download_results")
    assert resp.status_code == 404
