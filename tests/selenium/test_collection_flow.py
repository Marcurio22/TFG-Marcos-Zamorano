"""Pruebas Selenium de colección de imágenes.

Autor: Marcos Zamorano Lasso
Versión: 1.0
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
