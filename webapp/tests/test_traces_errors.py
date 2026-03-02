"""
Tests de errores del endpoint /traces.
(Falta cabecera)
"""

import os


def test_traces_404_when_not_calculated(client):
    resp = client.get("/traces")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data == {"error": "No hay trazas calculadas todavía."}


def test_traces_500_when_json_missing(client):
    # Forzamos en sesión un archivo inexistente
    missing = "missing_traces.json"
    out_dir = client.application.config["OUTPUT_FOLDER"]
    missing_path = os.path.join(out_dir, missing)

    # Aseguramos que no exista
    if os.path.exists(missing_path):
        os.remove(missing_path)

    with client.session_transaction() as sess:
        sess["traces_file"] = missing

    resp = client.get("/traces")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data == {
        "error": "Archivo de trazas no encontrado. Vuelve a calcularlas."}
