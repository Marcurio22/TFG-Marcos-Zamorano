"""Pruebas Selenium de subida y validación de modelos.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    by_css,
    clickable,
    create_user,
    css,
    login_through_ui,
    visible_css,
    wait_class,
    wait_for_model_validation_state,
    wait_for_text,
)

pytestmark = [
    pytest.mark.selenium,
    pytest.mark.filterwarnings(
        "ignore:.*torch\\.jit\\.trace.*is deprecated.*:"
        "DeprecationWarning"
    ),
    pytest.mark.filterwarnings(
        "ignore:.*torch\\.jit\\.trace_method.*is deprecated.*:"
        "DeprecationWarning"
    ),
]


MODEL_NAME = "modelo_validado_selenium_infer.pt"


def _write_valid_torchscript_model(tmp_path):
    """Crea un modelo TorchScript mínimo compatible con la validación."""
    torch = pytest.importorskip("torch")

    model = torch.nn.Sequential(
        torch.nn.Conv2d(3, 1, kernel_size=1),
        torch.nn.Sigmoid(),
    )
    with torch.no_grad():
        model[0].weight.fill_(0.05)
        model[0].bias.fill_(0.0)

    example = torch.ones(1, 3, 32, 32)
    traced = torch.jit.trace(model.eval(), example)
    model_path = tmp_path / MODEL_NAME
    traced.save(str(model_path))
    return model_path


def test_admin_uploaded_model_is_validated(
    browser,
    live_server,
    app,
    tmp_path,
):
    """El administrador sube un modelo y espera a que quede validado."""
    create_user(
        app,
        username="selenium_admin_validation",
        email="selenium_admin_validation@example.com",
        role="admin",
    )
    model_to_upload = _write_valid_torchscript_model(tmp_path)
    login_through_ui(browser, live_server, "selenium_admin_validation")

    browser.get(f"{live_server}/admin/folds/")
    wait_for_text(browser, "Gestión del Modelo")
    clickable(browser, "[data-upload-fold-button]").click()

    modal = css(browser, "#upload-fold-modal")
    wait = wait_class()(browser, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)

    visible_css(
        browser,
        "#upload-fold-modal input[name='fold_name']",
    ).send_keys(MODEL_NAME)
    css(
        browser,
        "#upload-fold-modal input[type='file']",
    ).send_keys(str(model_to_upload))
    clickable(
        browser,
        "#upload-fold-form button[type='submit']",
    ).click()

    wait_for_text(browser, "Modelo recibido")
    wait_for_text(browser, MODEL_NAME)

    row = wait_for_model_validation_state(
        browser,
        MODEL_NAME,
        "validado",
    )
    assert "VALIDADO" in row.text.upper()
    assert (
        "ACTIVO" in row.text.upper()
        or row.find_elements(by_css(), "[data-activate-fold-button]")
    )
