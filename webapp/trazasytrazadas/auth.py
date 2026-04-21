"""
===============================================================================
Rutas y utilidades de autenticación.

Define el registro de usuarios, el inicio de sesión, el perfil y la
integración base con Flask-Login.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db
from .forms import (
    LoginForm,
    ProfileForm,
    RegistrationForm,
    format_phone_number_for_display,
)
from .models import Usuario

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: str):
    """Recupera un usuario a partir del identificador guardado en sesión."""
    try:
        return db.session.get(Usuario, int(user_id))
    except (TypeError, ValueError):
        return None


def init_app(app) -> None:
    """Inicializa Flask-Login sobre la aplicación Flask."""
    login_manager.init_app(app)
    login_manager.login_view = "trazas.login"
    login_manager.login_message_category = "warning"


def _format_user_joined_at(value) -> str:
    """Devuelve la fecha de alta con formato DD/MM/AAAA."""
    if value is None:
        return "-"

    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")

    normalized = str(value).strip().replace(" ", "T")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return str(value)

    return parsed.strftime("%d/%m/%Y")


def register_auth_routes(bp) -> None:
    """Registra las rutas de autenticación sobre el blueprint principal."""

    @bp.route("/registro", methods=["GET", "POST"])
    def register():
        """Muestra el formulario de alta y crea usuarios nuevos."""
        if current_user.is_authenticated:
            return redirect(url_for("trazas.index"))

        form = RegistrationForm()

        if form.validate_on_submit():
            user = Usuario(
                nombre_usuario=form.nombre_usuario.data,
                correo_electronico=form.correo_electronico.data,
                telefono=(form.telefono.data or None),
                contrasena=generate_password_hash(form.contrasena.data),
                rol="user",
            )
            db.session.add(user)

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash(
                    _(
                        "No se ha podido completar el registro. "
                        "Revisa los datos e inténtalo de nuevo."
                    ),
                    "error",
                )
            else:
                flash(
                    _(
                        "Usuario registrado correctamente. "
                        "Ya puedes iniciar sesión."
                    ),
                    "success",
                )
                return redirect(url_for("trazas.login"))

        return render_template("register.html", form=form)

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        """Muestra el formulario de acceso y autentica usuarios."""
        if current_user.is_authenticated:
            return redirect(url_for("trazas.index"))

        form = LoginForm()

        if form.validate_on_submit():
            username = form.nombre_usuario.data

            try:
                user = db.session.execute(
                    select(Usuario).where(
                        func.lower(Usuario.nombre_usuario) == username.lower()
                    )
                ).scalar_one_or_none()
            except SQLAlchemyError:
                db.session.rollback()
                flash(
                    _(
                        "No se ha podido iniciar sesión. "
                        "Inténtalo de nuevo más tarde."
                    ),
                    "error",
                )
                return render_template("login.html", form=form)

            if user is None or not check_password_hash(
                user.contrasena,
                form.contrasena.data,
            ):
                flash(_("Usuario o contraseña incorrectos."), "error")
            else:
                login_user(user)
                flash(_("Has iniciado sesión correctamente."), "success")
                return redirect(url_for("trazas.index"))

        return render_template("login.html", form=form)

    @bp.route("/logout", methods=["POST"])
    @login_required
    def logout():
        """Cierra la sesión activa y vuelve a la portada."""
        logout_user()
        flash(_("Has cerrado sesión correctamente."), "success")
        return redirect(url_for("trazas.index"))

    @bp.route("/perfil", methods=["GET"])
    @login_required
    def profile():
        """Muestra la página de perfil del usuario autenticado."""
        form = ProfileForm(
            nombre_usuario=current_user.nombre_usuario,
            correo_electronico=current_user.correo_electronico,
            telefono=current_user.telefono or "",
        )
        return render_template(
            "profile.html",
            form=form,
            open_edit_form=False,
            joined_label=_format_user_joined_at(current_user.fecha_alta),
            phone_label=format_phone_number_for_display(current_user.telefono),
        )

    @bp.route("/perfil/editar", methods=["POST"])
    @login_required
    def update_profile():
        """Actualiza nombre, correo y teléfono del usuario autenticado."""
        form = ProfileForm()

        if form.validate_on_submit():
            current_user.nombre_usuario = form.nombre_usuario.data
            current_user.correo_electronico = form.correo_electronico.data
            current_user.telefono = form.telefono.data or None

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash(
                    _(
                        "No se ha podido actualizar el perfil. "
                        "Revisa los datos e inténtalo de nuevo."
                    ),
                    "error",
                )
            else:
                flash(_("Perfil actualizado correctamente."), "success")
                return redirect(url_for("trazas.profile"))

        return render_template(
            "profile.html",
            form=form,
            open_edit_form=True,
            joined_label=_format_user_joined_at(current_user.fecha_alta),
            phone_label=format_phone_number_for_display(current_user.telefono),
        )
