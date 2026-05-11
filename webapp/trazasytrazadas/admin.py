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

import csv
from datetime import datetime
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    request,
    url_for,
)
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_babel import gettext as _
from flask_login import current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
from reportlab.platypus import TableStyle
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .collection import COLLECTION_PER_PAGE_OPTIONS, _pagination_items
from .collection_store import (
    purge_staged_parcel_dirs,
    restore_staged_parcel_dirs,
    stage_parcel_dirs_for_delete,
)
from .db import db
from .forms import (
    AdminActionForm,
    AdminFoldRenameForm,
    AdminFoldUploadForm,
    AdminUserEditForm,
    format_phone_number_for_display,
)
from .model_store import (
    add_fold_file,
    delete_fold_file,
    get_active_fold_name,
    list_model_rows,
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


def _user_role_label(role: str) -> str:
    """Devuelve una etiqueta legible para el rol del usuario."""
    labels = {
        "admin": _("Administrador"),
        "system": _("Sistema"),
        "user": _("Usuario"),
    }
    return labels.get(role, role or "-")


def _user_export_rows(users: list[Usuario]) -> list[list[str]]:
    """Construye las filas comunes para exportación CSV/PDF."""
    rows = [
        [
            _("ID"),
            _("Usuario"),
            _("Correo electrónico"),
            _("Teléfono"),
            _("Rol"),
            _("Fecha de registro"),
        ]
    ]

    for user in users:
        rows.append(
            [
                str(user.usuario_id),
                user.nombre_usuario or "-",
                user.correo_electronico or "-",
                format_phone_number_for_display(user.telefono),
                _user_role_label(user.rol),
                _format_user_joined_at(user.fecha_alta),
            ]
        )

    return rows


def _pdf_cell_text(value) -> str:
    """Escapa texto para ReportLab evitando caracteres no soportados."""
    text = str(value if value is not None else "-")
    text = text.encode("latin-1", "replace").decode("latin-1")
    return escape(text)


def _build_users_pdf(users: list[Usuario]) -> bytes:
    """Genera un PDF con el listado completo de usuarios."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
        title=_("Listado de usuarios"),
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal_style = ParagraphStyle(
        "UserExportNormal",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )
    header_style = ParagraphStyle(
        "UserExportHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "UserExportCell",
        parent=styles["BodyText"],
        fontSize=7,
        leading=9,
    )

    generated_at = datetime.now().strftime("%d/%m/%Y, %H:%M")
    elements = [
        Paragraph(_pdf_cell_text(_("Listado de usuarios")), title_style),
        Paragraph(
            _pdf_cell_text(_("Generado el %(date)s", date=generated_at)),
            normal_style,
        ),
        Spacer(1, 0.35 * cm),
    ]

    table_data = []
    for row_index, row in enumerate(_user_export_rows(users)):
        style = header_style if row_index == 0 else cell_style
        table_data.append(
            [Paragraph(_pdf_cell_text(value), style) for value in row]
        )

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            1.2 * cm,
            4.0 * cm,
            6.1 * cm,
            3.8 * cm,
            3.0 * cm,
            4.2 * cm,
        ],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    colors.white,
                    colors.HexColor("#f8fafc"),
                ]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)

    return buffer.getvalue()


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

    def _users_for_export(self) -> list[Usuario]:
        """Devuelve todos los usuarios del sistema para exportación."""
        return db.session.execute(
            select(Usuario).order_by(Usuario.usuario_id.desc())
        ).scalars().all()

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

    @expose("/exportar/csv", methods=("GET",))
    def export_csv(self):
        """Exporta todos los usuarios visibles del sistema a CSV."""
        output = StringIO()
        output.write("\ufeff")

        writer = csv.writer(output)
        writer.writerows(_user_export_rows(self._users_for_export()))

        return Response(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=usuarios.csv"
            },
        )

    @expose("/exportar/pdf", methods=("GET",))
    def export_pdf(self):
        """Exporta todos los usuarios visibles del sistema a PDF."""
        pdf_bytes = _build_users_pdf(self._users_for_export())

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=usuarios.pdf"
            },
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
        """Elimina un usuario y sus parcelas asociadas."""
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

        parcel_ids = [
            int(parcel_id)
            for parcel_id in db.session.execute(
                select(Parcela.parcela_id).where(Parcela.usuario_id == user_id)
            ).scalars().all()
        ]
        parcel_count = len(parcel_ids)
        staged_paths: list[tuple[str | None, str | None]] = []

        try:
            staged_paths = stage_parcel_dirs_for_delete(parcel_ids)
            db.session.delete(user)
            db.session.commit()
        except (IntegrityError, SQLAlchemyError, OSError):
            db.session.rollback()
            restore_staged_parcel_dirs(staged_paths)
            flash(
                _(
                    "No se ha podido eliminar el usuario. "
                    "Inténtalo de nuevo más tarde."
                ),
                "error",
            )
        else:
            purge_staged_parcel_dirs(staged_paths)

            if parcel_count > 0:
                flash(
                    _(
                        "Usuario eliminado correctamente. También se han "
                        "eliminado %(count)s parcelas asociadas.",
                        count=parcel_count,
                    ),
                    "success",
                )
            else:
                flash(_("Usuario eliminado correctamente."), "success")

        return redirect(url_for("admin_usuarios.index_view"))


class FoldsAdminView(_AdminAccessMixin, BaseView):
    """Gestión de modelos del sistema."""

    @expose("/", methods=("GET",))
    def index(self):
        rows = list_model_rows()
        active_name = get_active_fold_name()

        return self.render(
            "admin/folds.html",
            fold_rows=rows,
            active_fold_name=active_name,
            action_form=AdminActionForm(),
            rename_form=AdminFoldRenameForm(),
            upload_form=AdminFoldUploadForm(),
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
            flash(_("El modelo seleccionado no es válido."), "error")
        except FileNotFoundError:
            flash(_("El modelo seleccionado no existe."), "error")
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
            flash(_("El modelo que intentas renombrar no existe."), "error")
        except FileExistsError:
            flash(_("Ya existe otro modelo con ese nombre."), "warning")
        except OSError:
            flash(_("No se ha podido renombrar el modelo."), "error")
        else:
            flash(_("Modelo renombrado correctamente."), "success")

        return redirect(url_for("admin_folds.index"))

    @expose("/subir", methods=("POST",))
    def upload(self):
        """Sube, valida y registra un nuevo modelo del sistema."""
        try:
            request.max_content_length = int(
                current_app.config.get(
                    "MODEL_UPLOAD_MAX_CONTENT_LENGTH",
                    512 * 1024 * 1024,
                )
            )
        except (TypeError, ValueError, AttributeError):
            pass

        form = AdminFoldUploadForm()
        if not form.validate_on_submit():
            for field_errors in form.errors.values():
                for error in field_errors:
                    flash(error, "warning")
            return redirect(url_for("admin_folds.index"))

        max_bytes = int(
            current_app.config.get(
                "MODEL_UPLOAD_MAX_CONTENT_LENGTH",
                512 * 1024 * 1024,
            )
        )
        if request.content_length and request.content_length > max_bytes:
            flash(
                _("El archivo de modelo supera el tamaño máximo permitido."),
                "warning",
            )
            return redirect(url_for("admin_folds.index"))

        from .segmentation_inference import validate_fold_model_file

        def _validate_uploaded_model(path):
            return validate_fold_model_file(
                str(path),
                use_gpu=bool(
                    current_app.config.get("MODEL_VALIDATION_USE_GPU", False)
                ),
                image_size=int(
                    current_app.config.get("MODEL_VALIDATION_IMAGE_SIZE", 128)
                ),
                source_filename=form.model_file.data.filename,
            )

        try:
            add_fold_file(
                fold_name=form.fold_name.data,
                file_storage=form.model_file.data,
                validator=_validate_uploaded_model,
            )
        except ValueError as exc:
            flash(str(exc), "warning")
        except FileExistsError:
            flash(_("Ya existe otro modelo con ese nombre."), "warning")
        except OSError:
            flash(_("No se ha podido guardar el modelo."), "error")
        else:
            flash(_("Modelo añadido y validado correctamente."), "success")

        return redirect(url_for("admin_folds.index"))

    @expose("/eliminar", methods=("POST",))
    def delete(self):
        """Elimina un modelo no activo del sistema."""
        form = AdminActionForm()
        if not form.validate_on_submit():
            abort(400)

        fold_name = (request.form.get("fold_name") or "").strip()

        try:
            delete_fold_file(fold_name)
        except ValueError as exc:
            flash(str(exc), "warning")
        except FileNotFoundError:
            flash(_("El modelo que intentas eliminar no existe."), "error")
        except OSError:
            flash(_("No se ha podido eliminar el modelo."), "error")
        else:
            flash(_("Modelo eliminado correctamente."), "success")

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
