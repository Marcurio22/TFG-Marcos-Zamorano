"""
==============================================================================
Pruebas Selenium del flujo de imagen individual.

Comprueba la subida de una imagen, el cálculo simulado de trazas y la
activación visual de controles gestionados por JavaScript.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    create_image_file,
    css,
    wait_class,
    wait_for_download,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_single_image_upload_calculate_and_draw_flow(
    app,
    browser,
    live_server,
    monkeypatch,
    tmp_path,
):
    """Una imagen individual se sube, calcula y activa trazas por JS."""
    from trazasytrazadas import traces as traces_module

    monkeypatch.setattr(
        traces_module,
        "compute_traces",
        lambda _image_path: {"xs": [1, 4, 8], "ys": [2, 5, 9]},
    )

    image_path = create_image_file(tmp_path)
    browser.get(f"{live_server}/")

    css(browser, "#image-input").send_keys(str(image_path))
    wait_for_text(browser, image_path.name)
    css(browser, "#calculate-btn").click()

    wait_for_text(browser, "Trazas calculadas")
    checkbox = css(browser, "#traces-drawn-checkbox")
    download_button = css(browser, "#download-btn")

    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: checkbox.is_selected())
    wait.until(lambda _driver: download_button.is_enabled())

    assert "btn-primary" in download_button.get_attribute("class")


def test_single_image_results_zip_can_be_downloaded(
    app,
    browser,
    live_server,
    monkeypatch,
    tmp_path,
):
    """Las trazas calculadas de una imagen se descargan en ZIP."""
    from trazasytrazadas import traces as traces_module

    monkeypatch.setattr(
        traces_module,
        "compute_traces",
        lambda _image_path: {"xs": [1, 4, 8], "ys": [2, 5, 9]},
    )

    image_path = create_image_file(tmp_path, "descarga.jpg")
    browser.get(f"{live_server}/")

    css(browser, "#image-input").send_keys(str(image_path))
    wait_for_text(browser, image_path.name)
    css(browser, "#calculate-btn").click()

    wait_for_text(browser, "Trazas calculadas")
    download_button = css(browser, "#download-btn")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: download_button.is_enabled())
    download_button.click()

    downloaded = wait_for_download(
        browser.selenium_download_dir,
        ".zip",
    )
    assert downloaded.name.endswith("_resultados.zip")
