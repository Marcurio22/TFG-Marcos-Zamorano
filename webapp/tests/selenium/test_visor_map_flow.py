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
    complete_pending_collection_photos,
    configure_visor_map_start,
    create_user,
    login_through_ui,
    open_visor_controls_modal,
    select_map_area_at_coordinates,
    visible_css,
    wait_class,
    wait_for_map_selection,
    wait_for_text,
    wait_for_url_contains,
    wait_for_zone_status,
)

pytestmark = pytest.mark.selenium

RURAL_CENTER_LAT = 39.8261
RURAL_CENTER_LNG = -3.9667
RURAL_START_ZOOM = 13
RURAL_SELECT_ZOOM = 15


def test_visor_map_selection_generates_grid(
    browser,
    live_server,
    app,
    monkeypatch,
):
    """El visor genera una zona, la abre y ve sus trazas completadas."""
    from trazasytrazadas import visor as visor_module

    create_user(
        app,
        username="selenium_map",
        email="selenium_map@example.com",
    )
    monkeypatch.setattr(
        visor_module,
        "_visor_probe_source",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        visor_module,
        "trigger_trace_worker",
        lambda flask_app: complete_pending_collection_photos(flask_app),
    )
    login_through_ui(browser, live_server, "selenium_map")

    configure_visor_map_start(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_START_ZOOM,
    )
    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")
    select_map_area_at_coordinates(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_SELECT_ZOOM,
    )
    wait_for_map_selection(browser)
    open_visor_controls_modal(browser)
    visible_css(
        browser,
        "#visor-controls-modal[open] #generate-grid-btn",
    ).click()

    wait_for_text(browser, "Abrir colección")
    clickable(browser, "#visor-alerts a[href$='/coleccion']").click()

    wait_for_url_contains(browser, "/coleccion")
    wait_for_text(browser, "Colección de imágenes")
    wait_for_zone_status(browser, "completed")


def test_visor_reset_button_clears_selected_area(browser, live_server, app):
    """El botón de reinicio limpia la selección dibujada en el visor."""
    create_user(
        app,
        username="selenium_map_reset",
        email="selenium_map_reset@example.com",
    )
    login_through_ui(browser, live_server, "selenium_map_reset")

    configure_visor_map_start(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_START_ZOOM,
    )
    browser.get(f"{live_server}/visor")
    wait_for_text(browser, "Lista de descargas")

    select_map_area_at_coordinates(
        browser,
        center_lat=RURAL_CENTER_LAT,
        center_lng=RURAL_CENTER_LNG,
        zoom=RURAL_SELECT_ZOOM,
    )
    wait_for_map_selection(browser)
    clickable(browser, "#reset-selection-btn").click()

    wait = wait_class()(browser, 8)
    wait.until(
        lambda driver: len(
            driver.find_elements(by_css(), ".leaflet-marker-icon")
        ) == 0
    )
