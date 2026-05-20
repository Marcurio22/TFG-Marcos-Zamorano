"""
==============================================================================
Pruebas Selenium del perfil de usuario.

Verifica la edición de datos personales y el flujo de confirmación de imagen de
perfil usando formularios reales de la interfaz.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    clickable,
    create_image_file,
    create_user,
    css,
    fill,
    login_through_ui,
    submit,
    visible_css,
    wait_for_text,
    wait_for_url_contains,
)

pytestmark = pytest.mark.selenium


def test_profile_information_can_be_updated(browser, live_server, app):
    """El usuario edita sus datos personales desde la pantalla de perfil."""
    create_user(
        app,
        username="selenium_profile",
        email="selenium_profile@example.com",
    )
    login_through_ui(browser, live_server, "selenium_profile")

    browser.get(f"{live_server}/perfil")
    wait_for_text(browser, "selenium_profile")
    wait_for_text(browser, "Editar información")
    clickable(browser, "details summary").click()

    fill(browser, "nombre_usuario", "selenium_profile_editado")
    fill(browser, "correo_electronico", "perfil_editado@example.com")
    fill(browser, "telefono", "611 22 33 44")
    submit(browser, "form[action$='/perfil/editar'] input[type='submit']")

    wait_for_text(browser, "Perfil actualizado correctamente")
    wait_for_text(browser, "selenium_profile_editado")
    wait_for_text(browser, "perfil_editado@example.com")


def test_profile_image_can_be_confirmed(browser, live_server, app, tmp_path):
    """El usuario sube una imagen y la confirma como avatar."""
    create_user(
        app,
        username="selenium_avatar",
        email="selenium_avatar@example.com",
    )
    login_through_ui(browser, live_server, "selenium_avatar")

    image_path = create_image_file(tmp_path, "avatar.jpg")
    browser.get(f"{live_server}/perfil")
    css(browser, "#profile-image-input").send_keys(str(image_path))

    wait_for_url_contains(browser, "/perfil/imagen")
    wait_for_text(browser, "Confirmar imagen de perfil")
    submit(browser, "form[action$='/perfil/imagen/confirmar'] button")

    wait_for_text(browser, "Imagen de perfil actualizada correctamente")
    clickable(browser, "label[for='app-drawer']").click()
    assert visible_css(browser, "a[href$='/perfil'] img").is_displayed()
