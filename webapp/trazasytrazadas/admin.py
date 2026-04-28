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

from datetime import datetime

from flask import abort, current_app, flash, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .collection import COLLECTION_PER_PAGE_OPTIONS, _pagination_items
from .db import db
from .forms import (
    AdminActionForm,
    AdminFoldRenameForm,
    AdminUserEditForm,
    format_phone_number_for_display,
)
from .model_store import (
    get_active_fold_name,
    list_fold_files,
    rename_fold_file,
    set_active_fold_name,
)
from .models import Parcela, Usuario


def _format_user_joined_at(value) -> str:
    """Devuelve la fecha de alta con formato DD/MM/AAAA, HH:mm."""
    if value is None:
        return "-"

    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y, %H:%M")

    normalized = str(value).strip().replace("T", " ")

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%d/%m/%Y, %H:%M")
        except ValueError:
            continue

    return str(value)


def _parse_positive_int(value, default: int) -> int:
    """Convierte un valor a entero positivo,
        devolviendo un fallback si falla."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed > 0 else default


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


class UserAdminView(_AdminAccessMixin, BaseView):
    """Vista propia de gestión de usuarios, integrada con la UI de la app."""

    def _get_user_or_404(self, user_id: int) -> Usuario:
        """Recupera un usuario o devuelve 404 si no existe."""
        user = db.session.get(Usuario, user_id)
        if user is None:
            abort(404)
        return user

    def _count_user_parcels(self, user_id: int) -> int:
        """Cuenta cuántas parcelas tiene asociadas un usuario."""
        return int(
            db.session.execute(
                select(func.count(Parcela.parcela_id)).where(
                    Parcela.usuario_id == user_id
                )
            ).scalar_one()
        )

    @expose("/")
    def index_view(self):
        """Muestra el listado paginado de usuarios."""
        search = (request.args.get("q") or "").strip()
        page = _parse_positive_int(request.args.get("page"), 1)
        per_page = _parse_positive_int(
            request.args.get("per_page"),
            COLLECTION_PER_PAGE_OPTIONS[0],
        )

        if per_page not in COLLECTION_PER_PAGE_OPTIONS:
            per_page = COLLECTION_PER_PAGE_OPTIONS[0]

        filters = []
        if search:
            search_pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(Usuario.nombre_usuario).like(search_pattern),
                    func.lower(Usuario.correo_electronico).like(
                        search_pattern),
                    func.lower(func.coalesce(Usuario.telefono, "")).like(
                        search_pattern
                    ),
                    func.lower(Usuario.rol).like(search_pattern),
                )
            )

        total_users = int(
            db.session.execute(
                select(func.count(Usuario.usuario_id))
            ).scalar_one()
        )
        total_admins = int(
            db.session.execute(
                select(func.count(Usuario.usuario_id)).where(
                    Usuario.rol == "admin"
                )
            ).scalar_one()
        )
        total_regular = int(
            db.session.execute(
                select(func.count(Usuario.usuario_id)).where(
                    Usuario.rol == "user"
                )
            ).scalar_one()
        )

        count_stmt = select(func.count(Usuario.usuario_id))
        users_stmt = select(Usuario).order_by(Usuario.usuario_id.desc())

        if filters:
            count_stmt = count_stmt.where(*filters)
            users_stmt = users_stmt.where(*filters)

        filtered_total = int(db.session.execute(count_stmt).scalar_one())
        total_pages = max(1, (filtered_total + per_page - 1) // per_page)

        if page > total_pages:
            page = total_pages

        users = db.session.execute(
            users_stmt.offset((page - 1) * per_page).limit(per_page)
        ).scalars().all()

        listing_rows = []
        for user in users:
            is_current_user = int(user.usuario_id) == int(
                current_user.usuario_id)
            is_system_user = user.rol == "system"
            is_admin_user = user.rol == "admin"

            listing_rows.append(
                {
                    "user": user,
                    "phone_label": format_phone_number_for_display(
                        user.telefono
                    ),
                    "joined_label": _format_user_joined_at(user.fecha_alta),
                    "can_delete": (
                        not is_system_user
                        and not is_current_user
                        and not is_admin_user
                    ),
                    "can_edit": not is_system_user,
                    "is_current_user": is_current_user,
                    "is_system_user": is_system_user,
                    "is_admin_user": is_admin_user,
                }
            )

        listing = {
            "users": listing_rows,
            "total": filtered_total,
            "page": page,
            "per_page": per_page,
            "search": search,
            "total_pages": total_pages,
        }

        return self.render(
            "admin/users.html",
            summary={
                "total_users": total_users,
                "total_admins": total_admins,
                "total_regular": total_regular,
            },
            listing=listing,
            per_page_options=COLLECTION_PER_PAGE_OPTIONS,
            pagination_items=_pagination_items(page, total_pages),
            action_form=AdminActionForm(),
        )

    @expose("/<int:user_id>")
    def detail_view(self, user_id: int):
        """Muestra la ficha detallada de un usuario."""
        user = self._get_user_or_404(user_id)
        parcel_count = self._count_user_parcels(user_id)

        is_current_user = int(user.usuario_id) == int(current_user.usuario_id)
        is_system_user = user.rol == "system"
        is_admin_user = user.rol == "admin"

        return self.render(
            "admin/user_detail.html",
            user=user,
            phone_label=format_phone_number_for_display(user.telefono),
            joined_label=_format_user_joined_at(user.fecha_alta),
            parcel_count=parcel_count,
            can_edit=(not is_system_user),
            can_delete=(
                not is_system_user
                and not is_current_user
                and not is_admin_user
                and parcel_count == 0
            ),
            is_current_user=is_current_user,
            is_system_user=is_system_user,
            is_admin_user=is_admin_user,
            action_form=AdminActionForm(),
        )

    @expose("/<int:user_id>/editar", methods=("GET", "POST"))
    def edit_view(self, user_id: int):
        """Permite editar un usuario desde el panel admin."""
        user = self._get_user_or_404(user_id)

        if user.rol == "system":
            flash(
                _(
                    "El usuario del sistema no puede "
                    "editarse desde esta vista."
                ),
                "warning",
            )
            return redirect(url_for("admin_usuarios.detail_view",
                                    user_id=user_id))

        form = AdminUserEditForm(obj=user, user_id=user_id)

        if form.validate_on_submit():
            requested_role = form.rol.data

            if user.rol == "admin" and requested_role != "admin":
                flash(
                    _(
                        "No se puede retirar el rol de administrador "
                        "desde esta vista."
                    ),
                    "warning",
                )
                return redirect(url_for("admin_usuarios.detail_view",
                                        user_id=user_id))

            user.nombre_usuario = form.nombre_usuario.data
            user.correo_electronico = form.correo_electronico.data
            user.telefono = form.telefono.data or None
            user.rol = "admin" if user.rol == "admin" else requested_role

            try:
                db.session.commit()
            except (IntegrityError, SQLAlchemyError):
                db.session.rollback()
                flash(
                    _(
                        "No se ha podido actualizar el usuario. "
                        "Revisa los datos e inténtalo de nuevo."
                    ),
                    "error",
                )
            else:
                flash(_("Usuario actualizado correctamente."), "success")
                return redirect(
                    url_for("admin_usuarios.detail_view", user_id=user_id)
                )

        return self.render(
            "admin/user_edit.html",
            user=user,
            form=form,
        )

    @expose("/<int:user_id>/eliminar", methods=("POST",))
    def delete_view(self, user_id: int):
        """Elimina un usuario si cumple las restricciones de seguridad."""
        form = AdminActionForm()
        if not form.validate_on_submit():
            abort(400)

        user = self._get_user_or_404(user_id)

        if user.rol == "system":
            flash(
                _("El usuario del sistema no puede eliminarse."),
                "warning",
            )
            return redirect(url_for("admin_usuarios.index_view"))

        if int(user.usuario_id) == int(current_user.usuario_id):
            flash(
                _("No puedes eliminar el usuario con el "
                  "que has iniciado sesión."),
                "warning",
            )
            return redirect(url_for("admin_usuarios.detail_view",
                                    user_id=user_id))

        if user.rol == "admin":
            flash(
                _("No se puede eliminar otro usuario administrador."),
                "warning",
            )
            return redirect(url_for("admin_usuarios.detail_view",
                                    user_id=user_id))

        parcel_count = self._count_user_parcels(user_id)
        if parcel_count > 0:
            flash(
                _(
                    "No se puede eliminar el usuario porque tiene "
                    "parcelas asociadas."
                ),
                "warning",
            )
            return redirect(url_for("admin_usuarios.detail_view",
                                    user_id=user_id))

        try:
            db.session.delete(user)
            db.session.commit()
        except (IntegrityError, SQLAlchemyError):
            db.session.rollback()
            flash(
                _(
                    "No se ha podido eliminar el usuario. "
                    "Inténtalo de nuevo más tarde."
                ),
                "error",
            )
        else:
            flash(_("Usuario eliminado correctamente."), "success")

        return redirect(url_for("admin_usuarios.index_view"))


class FoldsAdminView(_AdminAccessMixin, BaseView):
    """Gestión de folds/modelos del sistema."""

    @expose("/", methods=("GET",))
    def index(self):
        folds = list_fold_files()
        active_name = get_active_fold_name()

        rows = [
            {
                "name": fold["name"],
                "index": fold["index"],
                "is_active": fold["name"] == active_name,
            }
            for fold in folds
        ]

        return self.render(
            "admin/folds.html",
            models_dir=str(current_app.config["SEG_MODELS_DIR"]),
            fold_rows=rows,
            active_fold_name=active_name,
            action_form=AdminActionForm(),
            rename_form=AdminFoldRenameForm(),
        )

    @expose("/activar", methods=("POST",))
    def activate(self):
        form = AdminActionForm()
        if not form.validate_on_submit():
            abort(400)

        fold_name = (request.form.get("fold_name") or "").strip()

        try:
            set_active_fold_name(fold_name)
        except ValueError:
            flash(_("El fold seleccionado no es válido."), "error")
        except FileNotFoundError:
            flash(_("El fold seleccionado no existe."), "error")
        else:
            flash(_("Modelo activo actualizado correctamente."), "success")

        return redirect(url_for("admin_folds.index"))

    @expose("/renombrar", methods=("POST",))
    def rename(self):
        form = AdminFoldRenameForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for error in field_errors:
                    flash(error, "warning")
            return redirect(url_for("admin_folds.index"))

        try:
            rename_fold_file(
                current_name=form.current_name.data,
                new_name=form.new_name.data,
            )
        except ValueError as exc:
            flash(str(exc), "warning")
        except FileNotFoundError:
            flash(_("El fold que intentas renombrar no existe."), "error")
        except FileExistsError:
            flash(_("Ya existe otro fold con ese nombre."), "warning")
        except OSError:
            flash(_("No se ha podido renombrar el fold."), "error")
        else:
            flash(_("Fold renombrado correctamente."), "success")

        return redirect(url_for("admin_folds.index"))


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
