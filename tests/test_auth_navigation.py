"""
===============================================================================
Pruebas de navegación y accesos protegidos.

Este módulo verifica el comportamiento del menú, el drawer lateral y las
restricciones de acceso para usuarios anónimos, autenticados y administradores.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from tests.auth_helpers import _create_user


def test_drawer_shows_profile_and_logout_for_authenticated_user(app, client):
    """El drawer muestra perfil y logout para usuarios autenticados."""
    user_id = _create_user(
        app,
        username="usuario_menu",
        email="menu@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "usuario_menu" in html
    assert 'href="/perfil"' in html
    assert "Panel del Administrador" not in html


def test_drawer_shows_admin_panel_for_admin_user(app, client):
    """El drawer muestra el bloque admin solo a usuarios administradores."""
    admin_id = _create_user(
        app,
        username="admin_menu",
        email="admin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Panel del Administrador" in html
    assert "Gestión de Usuarios" in html
    assert "Gestión del Modelo" in html


def test_drawer_shows_login_for_anonymous_user(client):
    """El drawer muestra acceso a login cuando no hay sesión."""
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Iniciar sesión" in html
    assert "Perfil" not in html
    assert "Cerrar sesión" not in html


def test_anonymous_user_cannot_access_visor(client):
    """Un usuario anónimo no puede acceder al visor."""
    response = client.get("/visor", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_cannot_access_collection(client):
    """Un usuario anónimo no puede acceder a la colección."""
    response = client.get("/coleccion", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_cannot_access_profile(client):
    """Un usuario anónimo no puede acceder al perfil."""
    response = client.get("/perfil", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_panel_redirects_anonymous_user_to_login(client):
    """El panel admin redirige a login si el usuario es anónimo."""
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_panel_forbids_regular_user(app, client):
    """Un usuario normal no puede entrar en Flask-Admin."""
    user_id = _create_user(
        app,
        username="usuario_normal",
        email="normal@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 403


def test_admin_panel_redirects_admin_to_user_management(app, client):
    """El root admin redirige a la gestión de usuarios."""
    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert "/admin/usuarios" in response.headers["Location"]
