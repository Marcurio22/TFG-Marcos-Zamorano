"""
===============================================================================
Formularios de autenticación de la aplicación.

Define los formularios y validaciones de entrada para el alta de usuarios,
el inicio de sesión y la edición del perfil.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import re

from flask_babel import gettext as _, lazy_gettext as _l
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func, select
from wtforms import (
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
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
_PHONE_PREFIX_RE = re.compile(r"^\+(\d{2})(.*)$")


def normalize_phone_number(value: str | None) -> str | None:
    """Normaliza un teléfono y aplica +34 por defecto si no hay prefijo."""
    raw = " ".join((value or "").split()).strip()

    if not raw:
        return None

    if raw.startswith("+"):
        match = _PHONE_PREFIX_RE.match(raw)
        if match is None:
            raise ValueError(
                _(
                    "Si indicas prefijo internacional, debe empezar por "
                    "'+' seguido de dos dígitos juntos."
                )
            )
        country = match.group(1)
        rest = match.group(2).strip()
    else:
        country = "34"
        rest = raw

    if not rest:
        raise ValueError(
            _("Introduce el número de teléfono después del prefijo.")
        )

    if not re.fullmatch(r"[0-9 ]+", rest):
        raise ValueError(
            _("El teléfono solo puede contener dígitos y espacios.")
        )

    digits = rest.replace(" ", "")

    if len(digits) < 7:
        raise ValueError(
            _("El teléfono debe incluir al menos 7 dígitos.")
        )

    normalized = f"+{country}{digits}"

    if len(normalized) > 20:
        raise ValueError(
            _("El teléfono no puede superar los 20 caracteres.")
        )

    return normalized


def format_phone_number_for_display(value: str | None) -> str:
    """Formatea el teléfono para mostrarlo en perfil."""
    if not value:
        return _("No asociado")

    try:
        normalized = normalize_phone_number(value)
    except ValueError:
        return str(value)

    if not normalized:
        return _("No asociado")

    country = normalized[1:3]
    digits = normalized[3:]

    if len(digits) == 9:
        groups = [
            digits[:3],
            digits[3:5],
            digits[5:7],
            digits[7:9],
        ]
    else:
        groups = []
        remaining = digits

        if len(remaining) > 4:
            groups.append(remaining[:3])
            remaining = remaining[3:]

        while len(remaining) > 2:
            groups.append(remaining[:2])
            remaining = remaining[2:]

        if remaining:
            groups.append(remaining)

    return f"(+{country}) {' '.join(groups)}"


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
        """Normaliza y valida el teléfono opcional."""
        if not (field.data or "").strip():
            field.data = ""
            return

        try:
            normalized = normalize_phone_number(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        field.data = normalized or ""

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


class LoginForm(FlaskForm):
    """Formulario de inicio de sesión."""
    nombre_usuario = StringField(
        _l("Usuario"),
        validators=[
            DataRequired(message=_l("Introduce un nombre de usuario.")),
            Length(
                max=50,
                message=_l(
                    "El nombre de usuario no puede superar "
                    "los 50 caracteres."
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
    submit = SubmitField(_l("Iniciar sesión"))

    def validate_nombre_usuario(self, field) -> None:
        """Normaliza el nombre de usuario antes de validarlo."""
        normalized = " ".join((field.data or "").split()).strip()
        field.data = normalized

        if not normalized:
            raise ValidationError(_("Introduce un nombre de usuario."))


class ProfileForm(FlaskForm):
    """Formulario de edición de perfil de usuario."""
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
        ],
    )
    submit = SubmitField(_l("Guardar cambios"))

    def validate_nombre_usuario(self, field) -> None:
        """Valida nombre de usuario único excluyendo al usuario actual."""
        normalized = " ".join((field.data or "").split()).strip()
        field.data = normalized

        if not normalized:
            raise ValidationError(_("Introduce un nombre de usuario."))

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.nombre_usuario) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is None:
            return

        if (
            current_user.is_authenticated
            and int(existing) == int(current_user.usuario_id)
        ):
            return

        raise ValidationError(_("Ya existe un usuario con ese nombre."))

    def validate_correo_electronico(self, field) -> None:
        """Valida correo único excluyendo al usuario actual."""
        normalized = (field.data or "").strip().lower()
        field.data = normalized

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.correo_electronico) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is None:
            return

        if (
            current_user.is_authenticated
            and int(existing) == int(current_user.usuario_id)
        ):
            return

        raise ValidationError(
            _("Ya existe un usuario con ese correo electrónico.")
        )

    def validate_telefono(self, field) -> None:
        """Normaliza y valida el teléfono opcional."""
        if not (field.data or "").strip():
            field.data = ""
            return

        try:
            normalized = normalize_phone_number(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        field.data = normalized or ""


class AdminUserEditForm(FlaskForm):
    """Formulario de edición de usuarios desde el panel admin."""

    def __init__(self, *args, user_id: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id

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
        validators=[Optional()],
    )
    rol = SelectField(
        _l("Rol"),
        choices=[
            ("user", _l("Usuario")),
            ("admin", _l("Administrador")),
        ],
        validators=[
            DataRequired(message=_l("Selecciona un rol válido.")),
        ],
    )
    submit = SubmitField(_l("Guardar cambios"))

    def validate_nombre_usuario(self, field) -> None:
        """Valida nombre de usuario único excluyendo el usuario editado."""
        normalized = " ".join((field.data or "").split()).strip()
        field.data = normalized

        if not normalized:
            raise ValidationError(_("Introduce un nombre de usuario."))

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.nombre_usuario) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is None:
            return

        if self.user_id is not None and int(existing) == int(self.user_id):
            return

        raise ValidationError(_("Ya existe un usuario con ese nombre."))

    def validate_correo_electronico(self, field) -> None:
        """Valida correo único excluyendo el usuario editado."""
        normalized = (field.data or "").strip().lower()
        field.data = normalized

        existing = db.session.execute(
            select(Usuario.usuario_id).where(
                func.lower(Usuario.correo_electronico) == normalized.lower()
            )
        ).scalar_one_or_none()

        if existing is None:
            return

        if self.user_id is not None and int(existing) == int(self.user_id):
            return

        raise ValidationError(
            _("Ya existe un usuario con ese correo electrónico.")
        )

    def validate_telefono(self, field) -> None:
        """Normaliza y valida el teléfono opcional."""
        if not (field.data or "").strip():
            field.data = ""
            return

        try:
            normalized = normalize_phone_number(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        field.data = normalized or ""

    def validate_rol(self, field) -> None:
        """Restringe los roles editables desde el panel admin."""
        if field.data not in {"user", "admin"}:
            raise ValidationError(_("Selecciona un rol válido."))


class AdminActionForm(FlaskForm):
    """Formulario vacío para acciones protegidas por CSRF en admin."""


class AdminFoldRenameForm(FlaskForm):
    """Formulario para renombrar un fold del sistema."""

    current_name = HiddenField(
        _l("Nombre actual"),
        validators=[
            DataRequired(message=_l("Falta el nombre actual del fold.")),
        ],
    )
    new_name = StringField(
        _l("Nuevo nombre"),
        validators=[
            DataRequired(message=_l("Introduce un nombre para el fold.")),
            Length(
                min=1,
                max=100,
                message=_l(
                    "El nombre del fold debe tener entre 1 y 100 caracteres."
                ),
            ),
            Regexp(
                r"^[A-Za-z0-9._-]+$",
                message=_l(
                    "El nombre solo puede contener letras, números, puntos, "
                    "guiones y guiones bajos."
                ),
            ),
        ],
    )
    submit = SubmitField(_l("Guardar nombre"))

    def validate_new_name(self, field) -> None:
        """Normaliza y valida el nuevo nombre del fold."""
        value = (field.data or "").strip()
        field.data = value

        if value in {".", ".."}:
            raise ValidationError(_("Introduce un nombre de fold válido."))

        if "/" in value or "\\" in value:
            raise ValidationError(
                _("El nombre del fold no puede contener rutas.")
            )
