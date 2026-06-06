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
    configure_visor_map_start,
    create_user,
    css,
    login_through_ui,
    select_map_area_at_coordinates,
    visible_css,
    wait_class,
    wait_for_map_selection,
    wait_for_text,
)

pytestmark = pytest.mark.selenium

RURAL_CENTER_LAT = 39.8261
RURAL_CENTER_LNG = -3.9667
RURAL_START_ZOOM = 13
RURAL_SELECT_ZOOM = 15


def test_visor_controls_require_selection_before_modal(
    browser,
    live_server,
    app,
):
    """El visor avisa antes del modal si falta la selección."""
    create_user(
        app,
        username="selenium_visor",
        email="selenium_visor@example.com",
    )
    login_through_ui(browser, live_server, "selenium_visor")

    configure_visor_map_start(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_START_ZOOM,
    )
    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")

    open_button = css(browser, "#open-controls-btn")
    reset_button = css(browser, "#reset-selection-btn")
    modal = css(browser, "#visor-controls-modal")
    assert reset_button.get_attribute("title") == "Borrar selección"

    open_button.click()
    warning = visible_css(browser, "#visor-alerts .alert-warning")
    assert "Haz dos clics" in warning.text
    assert modal.get_attribute("open") is None

    select_map_area_at_coordinates(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_SELECT_ZOOM,
    )
    wait_for_map_selection(browser)
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
