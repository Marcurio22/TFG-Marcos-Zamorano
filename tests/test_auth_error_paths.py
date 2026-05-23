"""
===============================================================================
Pruebas de errores defensivos de autenticación y perfil.

Este módulo cubre ramas defensivas del manejo de imagen de perfil y errores de
persistencia del perfil de usuario.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

import trazasytrazadas.auth as auth_module
from tests.auth_helpers import _create_user, _disable_csrf
from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario


def _png_storage(filename="avatar.png") -> FileStorage:
    """Devuelve rutas temporales para imágenes de perfil."""
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color=(1, 2, 3)).save(buffer, format="PNG")
    buffer.seek(0)
    return FileStorage(
        stream=buffer, filename=filename, content_type="image/png"
    )


def _login_user(client, user_id: int) -> None:
    """Autentica un usuario normal para la prueba actual."""
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_profile_image_delete_and_size_helpers(app, tmp_path, monkeypatch):
    """Verifica la imagen de perfil en el caso previsto."""
    with app.app_context():
        app.config["PROFILE_IMAGE_FOLDER"] = str(tmp_path)
        image = tmp_path / "users" / "1" / "avatar.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"image")

        monkeypatch.setattr(
            auth_module.os,
            "remove",
            lambda path: (_ for _ in ()).throw(OSError("locked")),
        )
        auth_module._delete_profile_image_file("users/1/avatar.png")

        assert auth_module._file_storage_size(object()) is None

        class BrokenStream:
            def tell(self):
                """Registra una llamada simulada de filesystem."""
                raise OSError("broken")

        assert (
            auth_module._file_storage_size(
                type("S", (), {"stream": BrokenStream()})()
            )
            is None
        )


def test_save_profile_image_preview_reports_unusable_storage_paths(
    app, client, monkeypatch
):
    """Verifica que la imagen de perfil informa el caso previsto."""
    user_id = _create_user(
        app,
        username="profile_paths",
        email="profile_paths@example.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _login_user(client, user_id)

    with client:
        client.get("/perfil")
        monkeypatch.setattr(
            auth_module, "_profile_image_abspath", lambda relative_path: None
        )
        with pytest.raises(ValueError):
            auth_module._save_profile_image_preview(_png_storage())

    calls = {"count": 0}
    with client:
        client.get("/perfil")

        def fake_abspath(relative_path):
            """Devuelve una ruta absoluta simulada."""
            calls["count"] += 1
            if calls["count"] == 1:
                return app.config["PROFILE_IMAGE_FOLDER"]
            return None

        monkeypatch.setattr(
            auth_module, "_profile_image_abspath", fake_abspath
        )
        with pytest.raises(ValueError):
            auth_module._save_profile_image_preview(_png_storage())


def test_update_profile_commit_error_rerenders_edit_form(
    app, client, monkeypatch
):
    """Verifica el perfil de usuario en el caso previsto."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="profile_commit",
        email="profile_commit@example.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _login_user(client, user_id)

    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(
            IntegrityError("stmt", "params", "orig")
        ),
    )

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "profile_commit_2",
            "correo_electronico": "profile_commit_2@example.com",
            "telefono": "",
        },
    )

    assert response.status_code == 200
    assert "No se ha podido actualizar el perfil" in response.get_data(
        as_text=True
    )


def test_profile_image_preview_and_confirm_error_branches(
    app, client, tmp_path, monkeypatch
):
    """Verifica la imagen de perfil en el caso previsto."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="profile_confirm",
        email="profile_confirm@example.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _login_user(client, user_id)

    assert (
        client.post("/perfil/imagen/previsualizar", data={}).status_code == 302
    )
    assert client.post("/perfil/imagen/confirmar").status_code == 302

    app.config["PROFILE_IMAGE_FOLDER"] = str(tmp_path)
    preview = tmp_path / "tmp" / f"user_{user_id}" / "preview.png"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"preview")
    with client.session_transaction() as session:
        session[auth_module._PROFILE_IMAGE_SESSION_KEY] = (
            f"tmp/user_{user_id}/preview.png"
        )

    monkeypatch.setattr(
        auth_module.os,
        "replace",
        lambda src, dst: (_ for _ in ()).throw(OSError("disk")),
    )
    response = client.post("/perfil/imagen/confirmar")
    assert response.status_code == 302

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        assert user.ruta_imagen_perfil is None
