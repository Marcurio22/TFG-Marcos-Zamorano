"""
==============================================================================
Pruebas Selenium de gestión administrativa de modelos.

Ejercita acciones de activación y renombrado de modelos sobre los modales del
panel administrativo.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    clickable,
    create_demo_model,
    create_user,
    css,
    login_through_ui,
    visible_css,
    wait_class,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_admin_can_rename_model_from_modal(browser, live_server, app):
    """El administrador renombra un modelo desde su modal."""
    create_user(
        app,
        username="selenium_admin_model",
        email="selenium_admin_model@example.com",
        role="admin",
    )
    create_demo_model(app, "modelo_activo_selenium.pt")
    create_demo_model(app, "modelo_renombrable.pt", active=False)
    login_through_ui(browser, live_server, "selenium_admin_model")

    browser.get(f"{live_server}/admin/folds/")
    wait_for_text(browser, "modelo_renombrable.pt")
    clickable(
        browser,
        "[data-rename-fold-button][data-current-name='modelo_renombrable.pt']",
    ).click()

    modal = css(browser, "#rename-fold-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)

    new_name = visible_css(browser, "#rename-new-name")
    new_name.clear()
    new_name.send_keys("modelo_renombrado_selenium.pt")
    clickable(browser, "#rename-fold-form button[type='submit']").click()

    wait_for_text(browser, "Modelo renombrado correctamente")
    wait_for_text(browser, "modelo_renombrado_selenium.pt")


def test_admin_can_open_activation_modal(browser, live_server, app):
    """El administrador abre el modal de activación de modelo."""
    create_user(
        app,
        username="selenium_admin_activate",
        email="selenium_admin_activate@example.com",
        role="admin",
    )
    create_demo_model(app, "modelo_base_selenium.pt")
    create_demo_model(app, "modelo_para_activar.pt", active=False)
    login_through_ui(browser, live_server, "selenium_admin_activate")

    browser.get(f"{live_server}/admin/folds/")
    wait_for_text(browser, "modelo_para_activar.pt")
    clickable(
        browser,
        "[data-activate-fold-button][data-fold-name='modelo_para_activar.pt']",
    ).click()

    modal = css(browser, "#activate-fold-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)
    wait_for_text(browser, "modelo_para_activar.pt")
