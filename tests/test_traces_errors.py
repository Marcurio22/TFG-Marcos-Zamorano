"""
Pruebas de error para el endpoint /traces.

Este módulo cubre los casos en los que todavía no se han calculado trazas o en
los que la sesión referencia un fichero JSON que ya no existe en disco.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import os


def test_traces_404_when_not_calculated(client):
    """Debe devolver 404 si no hay un archivo de trazas asociado a la
    sesión."""
    resp = client.get("/traces")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data == {"error": "No hay trazas calculadas todavía."}


def test_traces_500_when_json_missing(client):
    """Debe devolver 500 si la sesión apunta a un JSON inexistente."""
    missing = "missing_traces.json"
    out_dir = client.application.config["OUTPUT_FOLDER"]
    missing_path = os.path.join(out_dir, missing)

    # Garantiza que el archivo referenciado no exista antes de la prueba.
    if os.path.exists(missing_path):
        os.remove(missing_path)

    with client.session_transaction() as sess:
        sess["traces_file"] = missing

    resp = client.get("/traces")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data == {
        "error": "Archivo de trazas no encontrado. Vuelve a calcularlas."
    }


def test_traces_500_when_json_corrupt(client):
    """Debe devolver 500 si el fichero existe pero contiene JSON inválido."""
    out_dir = client.application.config["OUTPUT_FOLDER"]
    corrupt_name = "corrupt_traces.json"
    corrupt_path = os.path.join(out_dir, corrupt_name)

    with open(corrupt_path, "w", encoding="utf-8") as f:
        f.write("{this-is:not-valid-json")

    with client.session_transaction() as sess:
        sess["traces_file"] = corrupt_name

    resp = client.get("/traces")
    assert resp.status_code == 500

    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data
