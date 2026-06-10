"""Pruebas de parciales compartidos de plantillas.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from tests.auth_helpers import (
    _create_user,
    _disable_csrf,
    _login_payload,
    _registration_payload,
)


def _assert_shared_head_assets(html: str) -> None:
    """Los recursos comunes de cabecera siguen renderizándose."""
    assert "cdn.jsdelivr.net/npm/daisyui@5" in html
    assert "cdn.jsdelivr.net/npm/@tailwindcss/browser@4" in html
    assert 'href="/static/style.css"' in html
    assert "img/favicon.png" in html
    assert "js/phone_input.js" in html


def test_auth_base_renders_shared_head_assets(client):
    """Login mantiene los recursos compartidos de auth_base."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    _assert_shared_head_assets(html)
    assert 'aria-label="Cambiar idioma"' in html
    assert "dropdown-content menu" in html
    assert "language-toggle-btn" in html
    assert "language-menu" in html


def test_base_renders_shared_head_assets_and_csrf(client):
    """Portada mantiene recursos comunes y metadato CSRF global."""
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    _assert_shared_head_assets(html)
    assert 'name="csrf-token"' in html
    assert 'id="app-drawer"' in html
    assert "language-toggle-btn" in html
    assert "language-menu" in html


def test_auth_base_keeps_flash_rendering(app, client):
    """Registro conserva los mensajes flash de auth_base."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario registrado correctamente." in html
    assert "toast toast-top toast-center z-50 mt-16" in html
    assert "alert alert-success shadow-lg" in html


def test_base_keeps_flash_rendering(app, client):
    """Login conserva los mensajes flash de base."""
    _disable_csrf(app)
    _create_user(
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
    assert "toast toast-top toast-center z-50 mt-4" in html
    assert "alert alert-success shadow-lg" in html
