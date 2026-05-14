"""
===============================================================================
Pruebas de validación y permisos de imagen de perfil.

Este módulo cubre validaciones y permisos de acceso de la imagen de perfil que
no quedan cubiertos por el flujo principal del perfil.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage

from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario
from trazasytrazadas import auth as auth_module


def _image_bytes(fmt="PNG", size=(24, 24)) -> BytesIO:
    """Construye una imagen PNG mínima para los tests."""
    buffer = BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def test_load_user_rejects_non_integer(app):
    """Verifica que el comportamiento esperado rechaza el caso previsto."""
    with app.app_context():
        assert auth_module.load_user("not-an-id") is None
        assert auth_module.load_user(None) is None


def test_auth_date_formatter_accepts_none_strings_and_unknown():
    """Verifica los formularios en el caso previsto."""
    assert auth_module._format_user_joined_at(None) == "-"
    assert (
        auth_module._format_user_joined_at("2024-01-02T03:04:05.000000")
        == "02/01/2024, 03:04"
    )
    assert (
        auth_module._format_user_joined_at("2024-01-02 03:04:05")
        == "02/01/2024, 03:04"
    )
    assert (
        auth_module._format_user_joined_at("2024-01-02 03:04")
        == "02/01/2024, 03:04"
    )
    assert auth_module._format_user_joined_at("sin-formato") == "sin-formato"


def test_profile_image_path_helpers_and_size_failures(app, force_login):
    """Verifica la imagen de perfil en el caso previsto."""
    force_login()
    with app.test_request_context("/"):
        assert auth_module._profile_image_abspath(None) is None
        assert auth_module._profile_image_abspath("../escape.png") is None
        assert auth_module._profile_image_extension("avatar") == ""
        assert auth_module._profile_image_extension("avatar.JPG") == "jpg"
        assert auth_module._profile_image_url(None) is None
        assert auth_module._profile_image_url("users/1/avatar.png").endswith(
            "/perfil/imagenes/users/1/avatar.png"
        )

        class BrokenStream(BytesIO):
            def tell(self):
                """Registra una llamada simulada de filesystem."""
                raise OSError("broken")

        storage = FileStorage(stream=BrokenStream(b"abc"), filename="a.png")
        assert auth_module._file_storage_size(storage) is None


def test_save_profile_image_preview_rejects_extension_size_and_corrupt_file(
    app, force_login
):
    """Verifica que la imagen de perfil rechaza el caso previsto."""
    user_id = force_login()
    app.config["PROFILE_IMAGE_MAX_BYTES"] = 5

    with app.test_request_context("/"):
        # Cargar current_user desde la sesión de test_request_context.
        from flask_login import login_user

        user = db.session.get(Usuario, user_id)
        login_user(user)

        bad_extension = FileStorage(
            stream=BytesIO(b"x"), filename="avatar.gif"
        )
        with pytest.raises(ValueError, match="JPG o PNG"):
            auth_module._save_profile_image_preview(bad_extension)

        too_large = FileStorage(
            stream=BytesIO(b"x" * 10), filename="avatar.png"
        )
        with pytest.raises(ValueError, match="4 MB"):
            auth_module._save_profile_image_preview(too_large)

        app.config["PROFILE_IMAGE_MAX_BYTES"] = 4 * 1024 * 1024
        corrupt = FileStorage(
            stream=BytesIO(b"not an image"), filename="avatar.png"
        )
        with pytest.raises(ValueError, match="imagen válida"):
            auth_module._save_profile_image_preview(corrupt)

        good = FileStorage(stream=_image_bytes("JPEG"), filename="avatar.jpg")
        relative = auth_module._save_profile_image_preview(good)
        absolute = auth_module._profile_image_abspath(relative)
        assert Path(absolute).exists()
        auth_module._delete_profile_image_file(relative)
        assert not Path(absolute).exists()


def test_profile_image_cancel_removes_pending_preview(
    client, app, force_login
):
    """Verifica la imagen de perfil en el caso previsto."""
    force_login()
    app.config["WTF_CSRF_ENABLED"] = False
    root = Path(app.config["PROFILE_IMAGE_FOLDER"])
    preview = root / "tmp" / "user_1" / "preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"x")

    with client.session_transaction() as session:
        session[auth_module._PROFILE_IMAGE_SESSION_KEY] = (
            "tmp/user_1/preview.png"
        )

    response = client.post("/perfil/imagen/cancelar", follow_redirects=True)
    assert response.status_code == 200
    assert not preview.exists()


def test_profile_image_file_permissions(client, app, force_login):
    """Verifica la imagen de perfil en el caso previsto."""
    owner_id = force_login(username="owner", email="owner@example.com")
    root = Path(app.config["PROFILE_IMAGE_FOLDER"])
    owner_path = root / "users" / str(owner_id) / "avatar.png"
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    owner_path.write_bytes(_image_bytes().getvalue())

    other_id = owner_id + 100
    other_path = root / "users" / str(other_id) / "avatar.png"
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_bytes(_image_bytes().getvalue())

    response = client.get(f"/perfil/imagenes/users/{owner_id}/avatar.png")
    assert response.status_code == 200
    response.close()

    response = client.get(f"/perfil/imagenes/users/{other_id}/avatar.png")
    assert response.status_code == 403
    assert client.get("/perfil/imagenes/../escape.png").status_code in {
        404,
        308,
    }
    assert client.get("/perfil/imagenes/missing.png").status_code == 404


def test_admin_can_serve_other_users_profile_image(client, app, force_login):
    """Verifica la imagen de perfil en el caso previsto."""
    force_login(username="admin", email="admin@example.com", role="admin")
    root = Path(app.config["PROFILE_IMAGE_FOLDER"])
    other_path = root / "users" / "999" / "avatar.png"
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_bytes(_image_bytes().getvalue())

    response = client.get("/perfil/imagenes/users/999/avatar.png")
    assert response.status_code == 200
    response.close()
