"""
===============================================================================
Rutas y utilidades de autenticación.

Define el registro de usuarios, el inicio de sesión y la integración base con
Flask-Login.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from flask import flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import LoginManager, current_user, login_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db
from .forms import LoginForm, RegistrationForm
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
                flash(_("Usuario registrado correctamente."), "success")
                return redirect(url_for("trazas.index"))

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
