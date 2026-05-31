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


def _canvas_has_red_pixels(browser) -> bool:
    """Indica si el canvas mantiene píxeles rojos de trazas."""
    return bool(
        browser.execute_script(
            """
            const canvas = document.querySelector('#traces-canvas');
            if (!canvas || !canvas.width || !canvas.height) return false;
            const ctx = canvas.getContext('2d');
            if (!ctx) return false;
            const data = ctx.getImageData(
              0,
              0,
              canvas.width,
              canvas.height
            ).data;
            for (let i = 0; i < data.length; i += 4) {
              if (
                data[i] > 200 &&
                data[i + 1] < 80 &&
                data[i + 2] < 80 &&
                data[i + 3] > 0
              ) {
                return true;
              }
            }
            return false;
            """
        )
    )


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


def test_single_image_traces_survive_window_resize(
    app,
    browser,
    live_server,
    monkeypatch,
    tmp_path,
):
    """Las trazas visibles se repintan tras redimensionar la ventana."""
    from trazasytrazadas import traces as traces_module

    monkeypatch.setattr(
        traces_module,
        "compute_traces",
        lambda _image_path: {
            "xs": [1, 4, 8, 16, 24, 30],
            "ys": [2, 5, 9, 12, 18, 22],
        },
    )

    image_path = create_image_file(tmp_path, "redimension.jpg")
    browser.get(f"{live_server}/")

    css(browser, "#image-input").send_keys(str(image_path))
    wait_for_text(browser, image_path.name)
    css(browser, "#calculate-btn").click()

    wait_for_text(browser, "Trazas calculadas")
    checkbox = css(browser, "#traces-drawn-checkbox")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: checkbox.is_selected())
    wait.until(_canvas_has_red_pixels)

    browser.execute_script("window.dispatchEvent(new Event('resize'));")

    wait.until(lambda _driver: checkbox.is_selected())
    wait.until(_canvas_has_red_pixels)


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
