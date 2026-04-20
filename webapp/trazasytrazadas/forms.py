"""
===============================================================================
Formularios de autenticación de la aplicación.

Define los formularios y validaciones de entrada para el alta de usuarios.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import re

from flask_babel import gettext as _, lazy_gettext as _l
from flask_wtf import FlaskForm
from sqlalchemy import func, select
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

from .db import db
from .models import Usuario

_USERNAME_RE = r"^[A-Za-zÀ-ÿ0-9_.-]+$"
_PHONE_RE = r"^[0-9+() \-]{7,20}$"


class RegistrationForm(FlaskForm):
    """Formulario de alta de nuevos usuarios."""
    nombre_usuario = StringField(
        _l("Usuario"),
        validators=[
            DataRequired(message=_l("Introduce un nombre de usuario.")),
            Length(
                min=3,
                max=50,
                message=_l(
                    "El nombre de usuario debe tener entre 3 y 50 caracteres."
                ),
            ),
            Regexp(
                _USERNAME_RE,
                message=_l(
                    "El nombre de usuario solo puede contener letras, "
                    "números, puntos, guiones y guiones bajos."
                ),
            ),
        ],
    )
    correo_electronico = StringField(
        _l("Correo electrónico"),
        validators=[
            DataRequired(message=_l("Introduce un correo electrónico.")),
            Length(
                max=50,
                message=_l(
                    "El correo electrónico no puede superar "
                    "los 50 caracteres."
                ),
            ),
            Email(message=_l("Introduce un correo electrónico válido.")),
        ],
    )
    telefono = StringField(
        _l("Teléfono (opcional)"),
        validators=[
            Optional(),
            Length(
                max=20,
                message=_l(
                    "El teléfono no puede superar los 20 caracteres."
                ),
            ),
            Regexp(
                _PHONE_RE,
                message=_l(
                    "Introduce un teléfono válido usando dígitos, espacios, "
                    "+, paréntesis o guiones."
                ),
            ),
        ],
    )
    contrasena = PasswordField(
        _l("Contraseña"),
        validators=[
            DataRequired(message=_l("Introduce una contraseña.")),
        ],
    )
    repetir_contrasena = PasswordField(
        _l("Repetir contraseña"),
        validators=[
            DataRequired(message=_l("Repite la contraseña.")),
            EqualTo(
                "contrasena",
                message=_l("Las contraseñas no coinciden."),
            ),
        ],
    )
    submit = SubmitField(_l("Registrarse"))

    def validate_nombre_usuario(self, field) -> None:
        """Comprueba formato y unicidad del nombre de usuario."""
        normalized = " ".join((field.data or "").split()).strip()
        field.data = normalized

        if not normalized:
            raise ValidationError(_("Introduce un nombre de usuario."))

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.nombre_usuario) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is not None:
            raise ValidationError(
                _("Ya existe un usuario con ese nombre.")
            )

    def validate_correo_electronico(self, field) -> None:
        """Normaliza y valida la unicidad del correo."""
        normalized = (field.data or "").strip().lower()
        field.data = normalized

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.correo_electronico) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is not None:
            raise ValidationError(
                _("Ya existe un usuario con ese correo electrónico.")
            )

    def validate_telefono(self, field) -> None:
        """Normaliza el teléfono opcional antes de persistirlo."""
        normalized = " ".join((field.data or "").split()).strip()
        field.data = normalized

    def validate_contrasena(self, field) -> None:
        """Aplica la política mínima de complejidad de contraseña."""
        value = field.data or ""

        if len(value) <= 8:
            raise ValidationError(
                _("La contraseña debe tener más de 8 caracteres.")
            )

        if not any(char.isupper() for char in value):
            raise ValidationError(
                _("La contraseña debe incluir al menos una mayúscula.")
            )

        if not any(char.isdigit() for char in value):
            raise ValidationError(
                _("La contraseña debe incluir al menos un número.")
            )

        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValidationError(
                _(
                    "La contraseña debe incluir al menos "
                    "un carácter especial."
                )
            )
