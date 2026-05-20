"""
==============================================================================
Pruebas Selenium de colección de imágenes.

Ejercita la lista de colecciones, la pausa/reanudación de cálculo y el estado
visual de botones gestionados por HTML y JavaScript.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    create_collection,
    create_user,
    css,
    login_through_ui,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_collection_pause_and_resume_from_listing(browser, live_server, app):
    """Una colección activa se pausa y reanuda desde el listado."""
    user_id = create_user(
        app,
        username="selenium_collection",
        email="selenium_collection@example.com",
    )
    create_collection(app, user_id=user_id)
    login_through_ui(browser, live_server, "selenium_collection")

    browser.get(f"{live_server}/coleccion")
    wait_for_text(browser, "Colección Selenium")

    pause_button = css(browser, "[data-zone-toggle-processing]")
    assert pause_button.get_attribute("aria-label") == "Pausar cálculo"
    pause_button.click()

    wait_for_text(browser, "El cálculo de trazas se ha pausado")
    resume_button = css(browser, "[data-zone-toggle-processing]")
    assert resume_button.get_attribute("aria-label") == "Reanudar cálculo"

    resume_button.click()
    wait_for_text(browser, "El cálculo de trazas se ha reanudado")
    pause_button = css(browser, "[data-zone-toggle-processing]")
    assert pause_button.get_attribute("aria-label") == "Pausar cálculo"


def test_completed_collection_has_disabled_pause_button(
    browser,
    live_server,
    app,
):
    """Una colección completada muestra la pausa deshabilitada."""
    user_id = create_user(
        app,
        username="selenium_completed",
        email="selenium_completed@example.com",
    )
    create_collection(
        app,
        user_id=user_id,
        name="Colección completada Selenium",
        photo_states=("completed", "completed"),
    )
    login_through_ui(browser, live_server, "selenium_completed")

    browser.get(f"{live_server}/coleccion")
    wait_for_text(browser, "Colección completada Selenium")

    pause_button = css(browser, "[data-zone-toggle-processing]")
    assert pause_button.get_attribute("aria-label") == "Trazas completadas"
    assert pause_button.get_attribute("aria-disabled") == "true"
    assert not pause_button.is_enabled()
