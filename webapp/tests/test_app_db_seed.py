"""
===============================================================================
Pruebas de configuración, bootstrap de base de datos y datos demo.

Este módulo cubre ramas de soporte de la app factory, db.py y seed_data.py que
no se ejercitan en los flujos funcionales principales.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trazasytrazadas import _env_bool, select_locale
from trazasytrazadas.db import db, _ensure_system_user, init_db_command
from trazasytrazadas.models import Foto, Parcela, Usuario
from trazasytrazadas.seed_data import (
    _copy_demo_storage,
    _execute_demo_sql,
    _is_database_empty,
    _read_sql_statements,
    load_demo_data_if_needed,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("si", True),
        ("sí", True),
        ("0", False),
    ],
)
def test_env_bool(monkeypatch, value, expected):
    """Verifica el comportamiento esperado en el caso previsto."""
    if value is None:
        monkeypatch.delenv("FEATURE_FLAG", raising=False)
        assert _env_bool("FEATURE_FLAG", True) is True
    else:
        monkeypatch.setenv("FEATURE_FLAG", value)
        assert _env_bool("FEATURE_FLAG") is expected


def test_select_locale_from_query_session_accept_language_and_default(app):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.test_request_context("/?lang=en"):
        assert select_locale() == "en"

    with app.test_request_context("/"):
        from flask import session

        session["lang"] = "fr"
        assert select_locale() == "fr"

    with app.test_request_context(
        "/", headers={"Accept-Language": "de-DE,de;q=0.9"}
    ):
        assert select_locale() == "de"

    with app.test_request_context("/", headers={"Accept-Language": "zz"}):
        assert select_locale() == "es"


def test_request_entity_too_large_handlers(client, app, force_login):
    """Verifica el comportamiento esperado en el caso previsto."""
    # Ruta no-admin: Flask aborta antes de la vista si supera el máximo.
    app.config["MAX_CONTENT_LENGTH"] = 1
    response = client.post("/upload", data={"image": (b"abc", "a.png")})
    assert response.status_code == 413

    # Ruta admin de modelos: el handler redirige al listado de modelos.
    app.config["WTF_CSRF_ENABLED"] = False
    force_login(role="admin")
    response = client.post(
        "/admin/folds/subir",
        data={"fold_name": "x", "model_file": (b"abc", "x.pt")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert "/admin/folds" in response.headers["Location"]


def test_context_processor_exposes_languages(app):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.test_request_context("/"):
        values = {}
        for processor in app.template_context_processors[None]:
            values.update(processor())
        assert "es" in values["LANGUAGES"]
        assert values["current_lang"] == "es"


def test_ensure_system_user_repairs_existing_row(app):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.app_context():
        system = db.session.get(Usuario, 1)
        system.nombre_usuario = "changed"
        system.contrasena = "bad"
        system.correo_electronico = "bad@example.com"
        system.rol = "user"
        db.session.commit()

        _ensure_system_user()
        repaired = db.session.get(Usuario, 1)
        assert repaired.nombre_usuario == "system"
        assert repaired.contrasena == "disabled"
        assert repaired.correo_electronico == "system@local.invalid"
        assert repaired.rol == "system"


def test_init_db_command_outputs_message(app, runner=None):
    """Verifica la base de datos en el caso previsto."""
    with app.app_context():
        result = app.test_cli_runner().invoke(init_db_command)
        assert result.exit_code == 0
        assert "Base de datos inicializada." in result.output


def test_seed_sql_reader_execute_copy_and_load(app, tmp_path):
    """Verifica la carga de datos iniciales en el caso previsto."""
    sql_file = tmp_path / "demo.sql"
    sql_file.write_text(
        "-- comment\n"
        "\n"
        "INSERT INTO usuario "
        "(usuario_id, nombre_usuario, contrasena, correo_electronico, rol)\n"
        "VALUES (50, 'demo', 'x', 'demo@example.com', 'user');\n"
        "INSERT INTO modelo (nombre_modelo, estado, validacion) "
        "VALUES ('demo-model', 'no_activo', 'validado')",
        encoding="utf-8",
    )
    statements = _read_sql_statements(sql_file)
    assert len(statements) == 2
    assert statements[0].startswith("INSERT INTO usuario")

    with app.app_context():
        assert _is_database_empty()
        _execute_demo_sql(sql_file)
        db.session.commit()
        assert db.session.get(Usuario, 50).nombre_usuario == "demo"
        assert not _is_database_empty()

        storage_source = tmp_path / "storage"
        (storage_source / "parcel").mkdir(parents=True)
        (storage_source / "parcel" / "tile.jpg").write_bytes(b"tile")
        _copy_demo_storage(storage_source)
        assert (
            Path(app.config["COLLECTION_STORAGE_ROOT"]) / "parcel" / "tile.jpg"
        ).exists()

        _copy_demo_storage(tmp_path / "missing-storage")


def test_load_demo_data_if_needed_disabled_missing_and_error(app, tmp_path):
    """Verifica el comportamiento esperado en el caso previsto."""
    with app.app_context():
        app.config["LOAD_DEMO_DATA"] = False
        load_demo_data_if_needed()

        app.config["LOAD_DEMO_DATA"] = True
        app.config["DEMO_SQL_FILE"] = str(tmp_path / "missing.sql")
        load_demo_data_if_needed()

        db.session.query(Usuario).filter(Usuario.rol != "system").delete()
        db.session.query(Parcela).delete()
        db.session.query(Foto).delete()
        db.session.commit()

        bad_sql = tmp_path / "bad.sql"
        bad_sql.write_text(
            "INSERT INTO tabla_que_no_existe VALUES (1);", encoding="utf-8"
        )
        app.config["DEMO_SQL_FILE"] = str(bad_sql)
        app.config["DEMO_STORAGE_DIR"] = str(tmp_path / "storage")
        with pytest.raises(Exception):
            load_demo_data_if_needed()
