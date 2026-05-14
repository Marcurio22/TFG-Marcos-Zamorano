"""
===============================================================================
Pruebas de validación de formularios y utilidades de formato.

Este módulo cubre validaciones unitarias de teléfonos, edición de usuario y
nombres de modelos que no quedan ejercitadas por los flujos funcionales.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import pytest
from flask_login import login_user
from werkzeug.datastructures import MultiDict

from tests.auth_helpers import _create_user
from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario
from trazasytrazadas.forms import (
    AdminFoldRenameForm,
    AdminFoldUploadForm,
    AdminUserEditForm,
    ProfileForm,
    RegistrationForm,
    format_phone_number_for_display,
    normalize_phone_number,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("  600   11 22 33 ", "+34600112233"),
        ("+33 600 11 22 33", "+33600112233"),
    ],
)
def test_normalize_phone_number_success(value, expected):
    """Verifica el comportamiento esperado en el caso previsto."""
    assert normalize_phone_number(value) == expected


@pytest.mark.parametrize(
    "value, message",
    [
        ("+A 600", "prefijo internacional"),
        ("+34", "después del prefijo"),
        ("600-112233", "dígitos y espacios"),
        ("123", "al menos 7"),
        ("+34 " + "1" * 30, "20 caracteres"),
    ],
)
def test_normalize_phone_number_errors(value, message):
    """Verifica el comportamiento esperado en el caso previsto."""
    with pytest.raises(ValueError, match=message):
        normalize_phone_number(value)


def test_format_phone_number_for_display_variants():
    """Verifica los formularios en el caso previsto."""
    assert "No asociado" in format_phone_number_for_display(None)
    assert "bad-phone" == format_phone_number_for_display("bad-phone")
    assert "No asociado" in format_phone_number_for_display("   ")
    assert format_phone_number_for_display("1234567") == "(+34) 123 45 67"
    assert format_phone_number_for_display("600112233") == "(+34) 600 11 22 33"


def test_registration_form_trims_empty_username_and_optional_phone(app):
    """Verifica los formularios en el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        empty_user = RegistrationForm(
            formdata=MultiDict(
                {
                    "nombre_usuario": "   ",
                    "correo_electronico": "new@example.com",
                    "telefono": "",
                    "contrasena": "Password1!",
                    "repetir_contrasena": "Password1!",
                }
            )
        )
        assert not empty_user.validate()
        assert (
            "Introduce un nombre de usuario."
            in empty_user.nombre_usuario.errors[0]
        )

        blank_phone = RegistrationForm(
            formdata=MultiDict(
                {
                    "nombre_usuario": "newuser",
                    "correo_electronico": "new@example.com",
                    "telefono": "   ",
                    "contrasena": "Password1!",
                    "repetir_contrasena": "Password1!",
                }
            )
        )
        assert blank_phone.validate()

        field = type("Field", (), {"data": "   "})()
        blank_phone.validate_telefono(field)
        assert field.data == ""


def test_profile_form_allows_current_user_duplicates_and_blank_phone(app):
    """Verifica que el perfil de usuario permite el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        user_id = _create_user(
            app, username="current", email="current@example.com"
        )
        user = db.session.get(Usuario, user_id)
        login_user(user)
        form = ProfileForm(
            formdata=MultiDict(
                {
                    "nombre_usuario": "current",
                    "correo_electronico": "current@example.com",
                    "telefono": "600 11 22 33",
                }
            )
        )
        assert form.validate()
        assert form.nombre_usuario.data == "current"
        assert form.correo_electronico.data == "current@example.com"
        assert form.telefono.data == "+34600112233"


def test_admin_user_edit_form_self_duplicates_blank_phone_and_invalid_role(
    app,
):
    """Verifica la administración de usuarios en el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        user_id = _create_user(
            app, username="adminedit", email="adminedit@example.com"
        )
        form = AdminUserEditForm(
            formdata=MultiDict(
                {
                    "nombre_usuario": "adminedit",
                    "correo_electronico": "adminedit@example.com",
                    "telefono": "600 11 22 33",
                    "rol": "user",
                }
            ),
            user_id=user_id,
        )
        assert form.validate()
        assert form.telefono.data == "+34600112233"

        field = type("Field", (), {"data": "   "})()
        form.validate_telefono(field)
        assert field.data == ""

        invalid_role = AdminUserEditForm(
            formdata=MultiDict(
                {
                    "nombre_usuario": "adminedit",
                    "correo_electronico": "adminedit@example.com",
                    "telefono": "600 11 22 33",
                    "rol": "system",
                }
            ),
            user_id=user_id,
        )
        assert not invalid_role.validate()
        assert "Opción inválida." in invalid_role.rol.errors[0]

        role_field = type("Field", (), {"data": "system"})()
        with pytest.raises(Exception, match="Selecciona un rol válido"):
            form.validate_rol(role_field)


@pytest.mark.parametrize("field_value", [".", ".."])
def test_admin_fold_forms_reject_dot_names(app, field_value):
    """Verifica que la gestión de modelos rechaza el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        rename = AdminFoldRenameForm(
            formdata=MultiDict(
                {"current_name": "old", "new_name": field_value}
            )
        )
        assert not rename.validate()
        assert (
            "Introduce un nombre de modelo válido."
            in rename.new_name.errors[0]
        )

        upload = AdminFoldUploadForm(
            formdata=MultiDict({"fold_name": field_value})
        )
        assert not upload.validate()
        assert (
            "Introduce un nombre de modelo válido."
            in upload.fold_name.errors[0]
        )


@pytest.mark.parametrize(
    "field_value, expected",
    [
        (".hidden", "no puede empezar por punto"),
        ("dir/model", "no puede contener rutas"),
        ("dir\\model", "no puede contener rutas"),
        ("bad:name", "caracteres no permitidos"),
    ],
)
def test_admin_fold_rename_form_rejects_unsafe_names(
    app, field_value, expected
):
    """Verifica que la gestión de modelos rechaza el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        form = AdminFoldRenameForm(
            formdata=MultiDict(
                {"current_name": "old", "new_name": field_value}
            )
        )
        assert not form.validate()
        assert expected in form.new_name.errors[0]


@pytest.mark.parametrize(
    "field_value, expected",
    [
        (".hidden", "no puede empezar por punto"),
        ("dir/model", "no puede contener rutas"),
        ("dir\\model", "no puede contener rutas"),
        ("bad:name", "caracteres no permitidos"),
    ],
)
def test_admin_fold_upload_form_rejects_unsafe_names(
    app, field_value, expected
):
    """Verifica que la gestión de modelos rechaza el caso previsto."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        form = AdminFoldUploadForm(
            formdata=MultiDict({"fold_name": field_value})
        )
        assert not form.validate()
        assert expected in form.fold_name.errors[0]
