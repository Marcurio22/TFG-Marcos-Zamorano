"""
===============================================================================
Panel de administración con Flask-Admin.

Define el acceso al panel de administración y sus vistas protegidas por rol.
Solo los usuarios autenticados con rol 'admin' podrán acceder.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import os

from flask import abort, current_app, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_babel import gettext as _
from flask_login import current_user

from .db import db
from .models import Usuario


class _AdminAccessMixin:
    """Mixin de control de acceso para vistas de Flask-Admin."""

    def is_accessible(self) -> bool:
        return (
            current_user.is_authenticated
            and getattr(current_user, "rol", None) == "admin"
        )

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("trazas.login", next=request.url))
        abort(403)


class SecureAdminIndexView(_AdminAccessMixin, AdminIndexView):
    """Índice principal del panel de administración."""

    @expose("/")
    def index(self):
        """Redirige al área útil de gestión de usuarios."""
        return redirect(url_for("admin_usuarios.index_view"))


class UserAdminView(_AdminAccessMixin, ModelView):
    """Vista de gestión de usuarios."""

    can_view_details = True
    can_create = False
    can_delete = False
    can_edit = True

    column_display_pk = True
    column_list = (
        "usuario_id",
        "nombre_usuario",
        "correo_electronico",
        "telefono",
        "rol",
        "fecha_alta",
    )
    column_searchable_list = (
        "nombre_usuario",
        "correo_electronico",
        "telefono",
    )
    column_filters = (
        "rol",
        "fecha_alta",
    )

    form_columns = (
        "nombre_usuario",
        "correo_electronico",
        "telefono",
        "rol",
    )
    form_choices = {
        "rol": [
            ("user", _("Usuario")),
            ("admin", _("Administrador")),
            ("system", _("Sistema")),
        ]
    }


class FoldsAdminView(_AdminAccessMixin, BaseView):
    """Vista simple para revisar la configuración de folds/modelos."""

    @expose("/")
    def index(self):
        models_dir = current_app.config["SEG_MODELS_DIR"]
        model_template = current_app.config["SEG_MODEL_TEMPLATE"]
        n_folds = int(current_app.config["SEG_N_FOLDS"])

        filenames = []
        if os.path.isdir(models_dir):
            filenames = sorted(os.listdir(models_dir))

        folds = []
        for fold in range(1, n_folds + 1):
            expected_base = model_template.format(fold=fold)
            matching_files = [
                filename for filename in filenames
                if expected_base in filename
            ]
            folds.append(
                {
                    "fold": fold,
                    "expected_base": expected_base,
                    "available_files": matching_files,
                    "configured": bool(matching_files),
                }
            )

        return self.render(
            "admin/folds.html",
            models_dir=models_dir,
            n_folds=n_folds,
            folds=folds,
        )


def init_admin(app):
    """Inicializa Flask-Admin y registra las vistas protegidas."""

    admin = Admin(
        app,
        name=_("Panel del Administrador"),
        index_view=SecureAdminIndexView(
            name=_("Panel del Administrador"),
            endpoint="admin",
            url="/admin",
        ),
        template_mode="bootstrap4",
    )

    admin.add_view(
        UserAdminView(
            Usuario,
            db.session,
            name=_("Gestión de Usuarios"),
            endpoint="admin_usuarios",
            url="/admin/usuarios",
            category=_("Administración"),
        )
    )

    admin.add_view(
        FoldsAdminView(
            name=_("Gestión del Modelo"),
            endpoint="admin_folds",
            url="/admin/folds",
            category=_("Administración"),
        )
    )

    return admin
