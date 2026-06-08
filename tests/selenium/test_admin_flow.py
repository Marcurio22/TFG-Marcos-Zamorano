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
    """El admin sube un modelo pendiente desde el modal de gestión."""
    from trazasytrazadas import admin as admin_module

    def skip_model_validation(*_args, **_kwargs):
        """Evita validar modelos en el flujo Selenium de subida."""
        return None

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        skip_model_validation,
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
    ).send_keys("modelo_a_cargar_selenium.pt")

    model_to_upload = tmp_path / "modelo_a_cargar_selenium.pt"
    model_to_upload.write_bytes(b"contenido de modelo de prueba")
    css(
        browser,
        "#upload-fold-modal input[type='file']",
    ).send_keys(str(model_to_upload))
    css(
        browser,
        "#upload-fold-form button[type='submit']",
    ).click()

    wait = wait_class()(browser, 15)
    wait.until(lambda driver: "/admin/folds" in driver.current_url)

    row_selector = (
        "tr[data-model-row]"
        "[data-model-name='modelo_a_cargar_selenium.pt']"
    )

    row = wait.until(
        lambda driver: (
            driver.find_elements("css selector", row_selector) or [False]
        )[0]
    )

    assert row.get_attribute("data-model-state") == "subiendo"
    assert row.get_attribute("data-model-validation") == "pendiente"
