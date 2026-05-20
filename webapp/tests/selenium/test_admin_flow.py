"""
==============================================================================
Pruebas Selenium del panel de administración.

Verifica navegación real por gestión de usuarios y modelos usando una cuenta
administradora y datos persistidos de prueba.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    create_demo_model,
    create_user,
    css,
    login_through_ui,
    visible_css,
    wait_class,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_admin_users_search_and_model_upload_modal(
    browser,
    live_server,
    app,
    monkeypatch,
    tmp_path,
):
    """El admin busca usuarios y sube un modelo pendiente desde el modal."""
    from trazasytrazadas import admin as admin_module

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        lambda *_args, **_kwargs: None,
    )

    create_user(
        app,
        username="selenium_admin",
        email="selenium_admin@example.com",
        role="admin",
    )
    create_user(
        app,
        username="usuario_objetivo",
        email="usuario_objetivo@example.com",
    )
    create_demo_model(app)
    login_through_ui(browser, live_server, "selenium_admin")

    browser.get(f"{live_server}/admin/usuarios/")
    wait_for_text(browser, "Gestión de Usuarios")

    search_input = css(browser, "input[name='q']")
    search_input.send_keys("usuario_objetivo")
    css(browser, "button[type='submit']").click()
    wait_for_text(browser, "usuario_objetivo")

    browser.get(f"{live_server}/admin/folds/")
    wait_for_text(browser, "Gestión del Modelo")
    wait_for_text(browser, "modelo_selenium.pt")

    css(browser, "[data-upload-fold-button]").click()
    modal = css(browser, "#upload-fold-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)
    wait_for_text(browser, "Añadir modelo")
    visible_css(
        browser,
        "#upload-fold-modal input[name='fold_name']",
    ).send_keys("modelo_malo_selenium.pt")

    bad_model = tmp_path / "modelo_malo_selenium.pt"
    bad_model.write_bytes(b"modelo no valido")
    css(
        browser,
        "#upload-fold-modal input[type='file']",
    ).send_keys(str(bad_model))
    css(
        browser,
        "#upload-fold-form button[type='submit']",
    ).click()

    wait_for_text(browser, "Modelo añadido correctamente")
    wait_for_text(browser, "modelo_malo_selenium.pt")
    wait_for_text(browser, "Pendiente")
