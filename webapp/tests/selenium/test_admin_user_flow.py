"""
==============================================================================
Pruebas Selenium de gestión administrativa de usuarios.

Valida el detalle y la edición de usuarios desde el panel de administración
con formularios reales y permisos de administrador.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import pytest

from tests.selenium.helpers import (
    clickable,
    create_user,
    css,
    fill,
    login_through_ui,
    select_option,
    submit,
    wait_for_text,
)

pytestmark = pytest.mark.selenium


def test_admin_can_view_and_edit_regular_user(browser, live_server, app):
    """El administrador edita un usuario desde el listado de gestión."""
    create_user(
        app,
        username="selenium_admin_edit",
        email="selenium_admin_edit@example.com",
        role="admin",
    )
    target_id = create_user(
        app,
        username="usuario_editable",
        email="usuario_editable@example.com",
    )
    login_through_ui(browser, live_server, "selenium_admin_edit")

    browser.get(f"{live_server}/admin/usuarios/")
    wait_for_text(browser, "Listado de usuarios")
    wait_for_text(browser, "usuario_editable")
    clickable(
        browser,
        f"a[href$='/admin/usuarios/{target_id}/editar']",
    ).click()

    wait_for_text(browser, "Editar usuario")
    username_input = css(browser, "input[name='nombre_usuario']")
    assert username_input.get_attribute("value") == "usuario_editable"
    fill(browser, "nombre_usuario", "usuario_editado_selenium")
    fill(browser, "correo_electronico", "editado_selenium@example.com")
    fill(browser, "telefono", "622 33 44 55")
    select_option(browser, "select[name='rol']", "admin")
    submit(browser, "input[type='submit']")

    wait_for_text(browser, "Usuario actualizado correctamente")
    wait_for_text(browser, "usuario_editado_selenium")
    wait_for_text(browser, "editado_selenium@example.com")


def test_admin_delete_user_from_listing(browser, live_server, app):
    """El administrador borra un usuario desde el modal del listado."""
    create_user(
        app,
        username="selenium_admin_delete",
        email="selenium_admin_delete@example.com",
        role="admin",
    )
    target_id = create_user(
        app,
        username="usuario_para_borrar",
        email="usuario_para_borrar@example.com",
    )
    login_through_ui(browser, live_server, "selenium_admin_delete")

    browser.get(f"{live_server}/admin/usuarios/")
    wait_for_text(browser, "usuario_para_borrar")
    css(
        browser,
        "[data-delete-user-button][data-user-name='usuario_para_borrar']",
    ).click()

    wait_for_text(browser, "Eliminar usuario")
    wait_for_text(browser, "usuario_para_borrar")
    css(browser, "#delete-user-form button[type='submit']").click()

    wait_for_text(browser, "Usuario eliminado correctamente")
    with app.app_context():
        from trazasytrazadas.db import db
        from trazasytrazadas.models import Usuario

        assert db.session.get(Usuario, target_id) is None
