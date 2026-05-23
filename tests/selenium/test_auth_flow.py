"""
==============================================================================
Pruebas Selenium de autenticación de usuarios.

Verifica registro, login, navegación autenticada y cierre de sesión usando el
HTML real y las interacciones de navegador.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    PASSWORD,
    clickable,
    css,
    fill,
    submit,
    wait_for_text,
    wait_for_url_contains,
)

pytestmark = pytest.mark.selenium


def test_register_login_and_logout_flow(browser, live_server):
    """Un usuario se registra, inicia sesión y cierra sesión desde la UI."""
    browser.get(f"{live_server}/registro")

    fill(browser, "nombre_usuario", "selenium_user")
    fill(browser, "correo_electronico", "selenium_user@example.com")
    fill(browser, "telefono", "600 12 34 56")
    fill(browser, "contrasena", PASSWORD)
    fill(browser, "repetir_contrasena", PASSWORD)
    submit(browser, "input[type='submit']")

    wait_for_url_contains(browser, "/login")
    wait_for_text(browser, "Usuario registrado correctamente")

    fill(browser, "nombre_usuario", "selenium_user")
    fill(browser, "contrasena", PASSWORD)
    submit(browser, "input[type='submit']")

    wait_for_text(browser, "Has iniciado sesión correctamente")
    wait_for_text(browser, "Sin imagen")

    clickable(browser, "label[for='app-drawer']").click()
    wait_for_text(browser, "Colección de imágenes")
    wait_for_text(browser, "selenium_user")

    logout_button = css(browser, "form[action$='/logout'] button")
    logout_button.click()
    wait_for_text(browser, "Has cerrado sesión correctamente")

    clickable(browser, "label[for='app-drawer']").click()
    wait_for_text(browser, "Iniciar sesión")
