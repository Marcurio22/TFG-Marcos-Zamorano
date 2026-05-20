"""
==============================================================================
Pruebas Selenium de galería de colección.

Ejercita el renombrado de colecciones y el visor ampliado de teselas con trazas
calculadas usando HTML y JavaScript reales.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    clickable,
    create_collection,
    create_user,
    css,
    login_through_ui,
    visible_css,
    wait_class,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_collection_can_be_renamed_from_listing(browser, live_server, app):
    """La colección se renombra desde el modal del listado."""
    user_id = create_user(
        app,
        username="selenium_rename",
        email="selenium_rename@example.com",
    )
    create_collection(app, user_id=user_id, name="Colección sin renombrar")
    login_through_ui(browser, live_server, "selenium_rename")

    browser.get(f"{live_server}/coleccion")
    wait_for_text(browser, "Colección sin renombrar")
    clickable(browser, "[data-action='open-zone-rename']").click()

    modal = css(browser, "#zone-rename-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)

    name_input = visible_css(browser, "#rename-zone-name-input")
    name_input.clear()
    name_input.send_keys("Colección renombrada Selenium")
    clickable(browser, "button[form='zone-rename-form']").click()

    wait_for_text(browser, "El nombre de la colección se ha actualizado")
    wait_for_text(browser, "Colección renombrada Selenium")


def test_gallery_photo_viewer_draws_completed_traces(
    browser,
    live_server,
    app,
):
    """La galería abre una tesela completada y permite dibujar trazas."""
    user_id = create_user(
        app,
        username="selenium_gallery",
        email="selenium_gallery@example.com",
    )
    create_collection(
        app,
        user_id=user_id,
        name="Colección galería Selenium",
        photo_states=("completed", "completed"),
    )
    login_through_ui(browser, live_server, "selenium_gallery")

    browser.get(f"{live_server}/coleccion")
    wait_for_text(browser, "Colección galería Selenium")
    clickable(browser, "a[href*='/galeria']").click()

    wait_for_text(browser, "Colección galería Selenium")
    clickable(browser, "[data-action='open-photo-viewer']").click()

    modal = css(browser, "#photo-viewer-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)
    wait_for_text(browser, "tile_1.jpg")

    draw_toggle = css(browser, "#photo-viewer-draw-toggle")
    assert draw_toggle.get_attribute("aria-disabled") == "false"
    draw_toggle.click()

    canvas = css(browser, "#photo-viewer-canvas")
    wait.until(lambda _driver: "hidden" not in canvas.get_attribute("class"))
