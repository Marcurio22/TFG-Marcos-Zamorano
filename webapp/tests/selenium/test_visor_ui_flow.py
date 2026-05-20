"""
==============================================================================
Pruebas Selenium del visor cartográfico.

Valida controles HTML/JS esenciales del visor sin depender de servicios WMS
externos ni de descargas reales de teselas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    create_user,
    css,
    login_through_ui,
    wait_class,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_visor_controls_modal_and_reset_button(browser, live_server, app):
    """El visor abre el modal y mantiene reinicio fuera del cuadro."""
    create_user(
        app,
        username="selenium_visor",
        email="selenium_visor@example.com",
    )
    login_through_ui(browser, live_server, "selenium_visor")

    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")

    open_button = css(browser, "#open-controls-btn")
    reset_button = css(browser, "#reset-selection-btn")
    assert reset_button.get_attribute("title") == "Borrar selección"

    modal = css(browser, "#visor-controls-modal")
    open_button.click()

    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)

    parent_dialog_id = browser.execute_script(
        "return arguments[0].closest('dialog')?.id || '';",
        reset_button,
    )
    assert parent_dialog_id == ""

    generate_parent_dialog_id = browser.execute_script(
        "return arguments[0].closest('dialog')?.id || '';",
        css(browser, "#generate-grid-btn"),
    )
    assert generate_parent_dialog_id == "visor-controls-modal"
