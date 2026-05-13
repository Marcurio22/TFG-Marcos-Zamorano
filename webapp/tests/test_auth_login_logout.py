"""
===============================================================================
Pruebas de inicio y cierre de sesión.

Este módulo verifica el flujo de login, logout, mantenimiento de sesión y
rechazo de credenciales inválidas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from trazasytrazadas.db import db
from tests.auth_helpers import (
    _create_user,
    _disable_csrf,
    _login_payload,
)


def test_login_page_renders(app, client):
    """La pantalla de login se renderiza correctamente."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Inicio de sesi" in html
    assert "Iniciar sesi" in html


def test_login_authenticates_user_and_stores_session(app, client):
    """Un login válido autentica al usuario y guarda la sesión."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Has iniciado sesi" in html

    with client.session_transaction() as session:
        assert session.get("_user_id") == str(user_id)
        assert session.get("_fresh") is True


def test_login_rejects_wrong_password(app, client):
    """No autentica si la contraseña es incorrecta."""
    _disable_csrf(app)
    _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    response = client.post(
        "/login",
        data=_login_payload(contrasena="Password2!"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario o contrase" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_rejects_unknown_user(app, client):
    """No autentica si el usuario no existe."""
    _disable_csrf(app)

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario o contrase" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_rejects_missing_fields(app, client):
    """El formulario informa los campos obligatorios vacíos."""
    _disable_csrf(app)

    response = client.post(
        "/login",
        data={
            "nombre_usuario": "",
            "contrasena": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Introduce un nombre de usuario." in html
    assert "Introduce una contrase" in html


def test_login_redirects_authenticated_user(app, client):
    """Un usuario autenticado no debe ver la pantalla de login."""
    user_id = _create_user(
        app,
        username="ya_logueado",
        email="logueado@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_login_handles_database_error(app, client, monkeypatch):
    """Se muestra un error genérico si falla la consulta a base de datos."""
    _disable_csrf(app)

    def _raise_db_error(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(db.session, "execute", _raise_db_error)

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No se ha podido iniciar sesi" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_logout_clears_session_and_redirects_home(app, client):
    """Cerrar sesión limpia la sesión activa y vuelve a portada."""
    user_id = _create_user(
        app,
        username="usuario_logout",
        email="logout@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post("/logout", follow_redirects=True)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Has cerrado sesi" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_logout_requires_authenticated_user(client):
    """Logout exige una sesión autenticada."""
    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_renders_guest_access_button(client):
    """La pantalla de login ofrece acceso a la parte básica como visitante."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Continuar como visitante" in html
