"""Pruebas de validación de formularios y utilidades de formato.

Autor: Marcos Zamorano Lasso
Versión: 1.0
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
    """Comprueba normalización correcta de teléfonos."""
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
    """Comprueba errores de normalización de teléfonos."""
    with pytest.raises(ValueError, match=message):
        normalize_phone_number(value)


def test_format_phone_number_for_display_variants():
    """Comprueba variantes de formato visual de teléfono."""
    assert "No asociado" in format_phone_number_for_display(None)
    assert "bad-phone" == format_phone_number_for_display("bad-phone")
    assert "No asociado" in format_phone_number_for_display("   ")
    assert format_phone_number_for_display("1234567") == "(+34) 123 45 67"
    assert format_phone_number_for_display("600112233") == "(+34) 600 11 22 33"


def test_registration_form_trims_empty_username_and_optional_phone(app):
    """Comprueba limpieza de usuario vacío y teléfono opcional en registro."""
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
    """Comprueba que el perfil permite conservar datos
        propios y teléfono vacío."""
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
    """Comprueba edición admin con datos propios,
        teléfono vacío y rol inválido."""
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
    """Comprueba que formularios de modelo rechazan nombres ocultos."""
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
    """Comprueba que el renombrado rechaza nombres de modelo inseguros."""
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
    """Comprueba que la subida rechaza nombres de modelo inseguros."""
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context("/"):
        form = AdminFoldUploadForm(
            formdata=MultiDict({"fold_name": field_value})
        )
        assert not form.validate()
        assert expected in form.fold_name.errors[0]
