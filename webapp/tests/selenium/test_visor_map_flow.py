"""
==============================================================================
Pruebas Selenium de interacción básica con el mapa.

Comprueba que Leaflet acepta selección por clics, genera la cuadrícula usando
backend simulado y permite reiniciar la selección desde la interfaz.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    by_css,
    clickable,
    create_user,
    login_through_ui,
    open_visor_controls_modal,
    select_map_area_near_center,
    visible_css,
    wait_class,
    wait_for_grid_ready,
    wait_for_map_selection,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_visor_map_selection_generates_grid(browser, live_server, app):
    """El visor selecciona un área y genera una cuadrícula sin WMS externo."""
    from trazasytrazadas import visor as visor_module

    create_user(
        app,
        username="selenium_map",
        email="selenium_map@example.com",
    )
    visor_module._visor_probe_source = lambda *_args, **_kwargs: True
    login_through_ui(browser, live_server, "selenium_map")

    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")
    select_map_area_near_center(browser)
    wait_for_map_selection(browser)
    open_visor_controls_modal(browser)
    visible_css(
        browser,
        "#visor-controls-modal[open] #generate-grid-btn",
    ).click()

    wait_for_grid_ready(browser)


def test_visor_reset_button_clears_selected_area(browser, live_server, app):
    """El botón de reinicio limpia la selección dibujada en el visor."""
    create_user(
        app,
        username="selenium_map_reset",
        email="selenium_map_reset@example.com",
    )
    login_through_ui(browser, live_server, "selenium_map_reset")

    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")

    select_map_area_near_center(browser)
    wait_for_map_selection(browser)
    clickable(browser, "#reset-selection-btn").click()

    wait = wait_class()(browser, 8)
    wait.until(
        lambda driver: len(
            driver.find_elements(by_css(), ".leaflet-marker-icon")
        ) == 0
    )
