"""
===============================================================================
Pruebas del perfil de usuario.

Este módulo verifica la visualización y edición del perfil, la actualización de
datos personales y el flujo básico de imagen de perfil.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario
from tests.auth_helpers import (
    _create_user,
    _disable_csrf,
    _profile_image_bytes,

)


def test_profile_requires_login(client):
    """La página de perfil exige autenticación."""
    response = client.get("/perfil", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_page_renders_current_user_data(app, client):
    """El perfil muestra datos del usuario autenticado."""
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        joined_label = user.fecha_alta.strftime("%d/%m/%Y, %H:%M")

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Nicoup" in html
    assert "nickurio@gmail.com" in html
    assert "No asociado" in html
    assert joined_label in html
    assert "Acceder al visor" in html
    assert "Acceder a la colección" in html


def test_profile_image_preview_shows_confirmation(app, client):
    """Subir una imagen válida muestra la pantalla de confirmación."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="AvatarUser",
        email="avatar@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/imagen/previsualizar",
        data={"profile_image": (_profile_image_bytes(), "avatar.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Confirmar imagen de perfil" in html
    assert "Guardar imagen" in html


def test_profile_image_confirm_persists_avatar(app, client):
    """Confirmar una imagen actualiza usuario y guarda el archivo local."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="AvatarUser",
        email="avatar@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    preview_response = client.post(
        "/perfil/imagen/previsualizar",
        data={"profile_image": (_profile_image_bytes(), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert preview_response.status_code == 200

    response = client.post(
        "/perfil/imagen/confirmar",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Imagen de perfil actualizada correctamente." in response.get_data(
        as_text=True
    )

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        assert user.ruta_imagen_perfil == f"users/{user_id}/avatar.png"
        image_path = Path(
            app.config["PROFILE_IMAGE_FOLDER"]) / user.ruta_imagen_perfil
        assert image_path.exists()

    image_response = client.get(f"/perfil/imagenes/users/{user_id}/avatar.png")
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/png"


def test_profile_image_preview_rejects_invalid_extension(app, client):
    """La imagen de perfil solo admite extensiones de imagen soportadas."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="AvatarUser",
        email="avatar@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/imagen/previsualizar",
        data={"profile_image": (BytesIO(b"no-image"), "avatar.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "La imagen de perfil debe ser JPG o PNG." in response.get_data(
        as_text=True
    )


def test_profile_update_persists_changes(app, client):
    """Editar perfil actualiza nombre, correo y teléfono en base de datos."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "NicoupEditado",
            "correo_electronico": "nicoupeditado@gmail.com",
            "telefono": "+34 660 36 46 51",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Perfil actualizado correctamente." in html

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        assert user.nombre_usuario == "NicoupEditado"
        assert user.correo_electronico == "nicoupeditado@gmail.com"
        assert user.telefono == "+34660364651"


def test_profile_update_rejects_duplicate_username(app, client):
    """No permite reutilizar un nombre de usuario ya existente."""
    _disable_csrf(app)
    owner_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _create_user(
        app,
        username="UsuarioExistente",
        email="otro@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "UsuarioExistente",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ya existe un usuario con ese nombre." in response.get_data(
        as_text=True)


def test_profile_update_rejects_duplicate_email(app, client):
    """No permite reutilizar un correo ya existente."""
    _disable_csrf(app)
    owner_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _create_user(
        app,
        username="OtroUsuario",
        email="existente@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "existente@gmail.com",
            "telefono": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ya existe un usuario con ese correo electr" in response.get_data(
        as_text=True)


def test_profile_update_rejects_invalid_phone(app, client):
    """No permite guardar teléfonos con formato inválido."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "telefono@@@",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "solo puede contener" in response.get_data(as_text=True)


def test_profile_page_formats_phone_for_display(app, client):
    """El perfil muestra el teléfono con formato legible estable."""
    user_id = _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
        phone="+34903389323",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "(+34) 903 38 93 23" in html


def test_profile_update_rejects_too_short_phone(app, client):
    """El perfil rechaza teléfonos demasiado cortos."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "+34909",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos 7 dígitos" in response.get_data(as_text=True)


def test_profile_page_shows_admin_badge_for_admin(app, client):
    """El perfil muestra la etiqueta de administrador solo para admins."""
    admin_id = _create_user(
        app,
        username="AdminUser",
        email="adminuser@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        user = db.session.get(Usuario, admin_id)
        joined_label = user.fecha_alta.strftime("%d/%m/%Y, %H:%M")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Administrador" in html
    assert joined_label in html


def test_profile_page_shows_admin_links_for_admin(app, client):
    """El perfil del administrador muestra accesos de gestión."""
    admin_id = _create_user(
        app,
        username="AdminUser",
        email="adminuser@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Administrador" in html
    assert "Gestión de Usuarios" in html
    assert "Gestión del Modelo" in html
