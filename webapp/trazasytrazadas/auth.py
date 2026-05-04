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
import os
from uuid import uuid4

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
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
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, UnidentifiedImageError

from .db import db
from .forms import (
    LoginForm,
    ProfileForm,
    ProfileImageConfirmForm,
    ProfileImageForm,
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


_PROFILE_IMAGE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
_PROFILE_IMAGE_SIZE = (512, 512)
_PROFILE_IMAGE_SESSION_KEY = "profile_image_preview_path"

try:
    _IMAGE_RESAMPLING = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - compatibilidad con Pillow antiguo.
    _IMAGE_RESAMPLING = Image.LANCZOS


def _profile_image_storage_root() -> str:
    """Devuelve y crea la carpeta raíz de imágenes de perfil."""
    root = current_app.config["PROFILE_IMAGE_FOLDER"]
    os.makedirs(root, exist_ok=True)
    return root


def _profile_image_abspath(relative_path: str | None) -> str | None:
    """Convierte una ruta relativa de perfil en ruta absoluta segura."""
    if not relative_path:
        return None

    root = os.path.abspath(_profile_image_storage_root())
    absolute_path = os.path.abspath(os.path.join(root, relative_path))

    if os.path.commonpath([root, absolute_path]) != root:
        return None

    return absolute_path


def _delete_profile_image_file(relative_path: str | None) -> None:
    """Borra una imagen de perfil si pertenece al almacenamiento esperado."""
    absolute_path = _profile_image_abspath(relative_path)
    if absolute_path and os.path.exists(absolute_path):
        try:
            os.remove(absolute_path)
        except OSError:
            current_app.logger.warning(
                "No se pudo eliminar la imagen de perfil %s.",
                relative_path,
                exc_info=True,
            )


def _clear_pending_profile_image() -> None:
    """Elimina la previsualización temporal pendiente, si existe."""
    pending_path = session.pop(_PROFILE_IMAGE_SESSION_KEY, None)
    _delete_profile_image_file(pending_path)


def _profile_image_extension(filename: str | None) -> str:
    """Extrae la extensión normalizada de un nombre de fichero."""
    safe_name = secure_filename(filename or "")
    if "." not in safe_name:
        return ""
    return safe_name.rsplit(".", 1)[1].lower()


def _file_storage_size(file_storage) -> int | None:
    """Devuelve el tamaño de un FileStorage sin consumir su stream."""
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return None

    try:
        current_position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current_position)
        return int(size)
    except (OSError, ValueError):
        return None


def _save_profile_image_preview(file_storage) -> str:
    """
    Valida, recorta y guarda una imagen temporal para confirmación.

    Devuelve la ruta relativa dentro de PROFILE_IMAGE_FOLDER.
    """
    extension = _profile_image_extension(file_storage.filename)
    if extension not in _PROFILE_IMAGE_ALLOWED_EXTENSIONS:
        raise ValueError(_("La imagen de perfil debe ser JPG o PNG."))

    max_bytes = int(current_app.config.get(
        "PROFILE_IMAGE_MAX_BYTES", 4 * 1024 * 1024))
    file_size = _file_storage_size(file_storage)
    if file_size is not None and file_size > max_bytes:
        raise ValueError(_("La imagen de perfil no puede superar los 4 MB."))

    user_dir = os.path.join("tmp", f"user_{current_user.usuario_id}")
    absolute_dir = _profile_image_abspath(user_dir)
    if absolute_dir is None:
        raise ValueError(_("No se ha podido preparar la imagen de perfil."))
    os.makedirs(absolute_dir, exist_ok=True)

    relative_path = f"{user_dir}/preview_{uuid4().hex}.png"
    absolute_path = _profile_image_abspath(relative_path)
    if absolute_path is None:
        raise ValueError(_("No se ha podido preparar la imagen de perfil."))

    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            image = ImageOps.fit(
                image,
                _PROFILE_IMAGE_SIZE,
                method=_IMAGE_RESAMPLING,
                centering=(0.5, 0.5),
            )
            image.save(absolute_path, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        _delete_profile_image_file(relative_path)
        raise ValueError(
            _("El archivo seleccionado no es una imagen válida.")) from exc

    return relative_path


def _final_profile_image_path(user_id: int) -> str:
    """Ruta relativa estable de la imagen definitiva de un usuario."""
    return f"users/{int(user_id)}/avatar.png"


def _profile_image_url(relative_path: str | None) -> str | None:
    """Genera la URL pública interna de una imagen de perfil."""
    if not relative_path:
        return None
    return url_for("trazas.profile_image_file", filename=relative_path)


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
        image_form = ProfileImageForm()
        return render_template(
            "profile.html",
            form=form,
            image_form=image_form,
            profile_image_url=_profile_image_url(
                current_user.ruta_imagen_perfil
            ),
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

        image_form = ProfileImageForm()
        return render_template(
            "profile.html",
            form=form,
            image_form=image_form,
            profile_image_url=_profile_image_url(
                current_user.ruta_imagen_perfil
            ),
            open_edit_form=True,
            joined_label=_format_user_joined_at(current_user.fecha_alta),
            phone_label=format_phone_number_for_display(current_user.telefono),
        )

    @bp.route("/perfil/imagen/previsualizar", methods=["POST"])
    @login_required
    def profile_image_preview():
        """Recibe una imagen de perfil y muestra una pantalla de confirmación."""
        form = ProfileImageForm()
        if not form.validate_on_submit():
            flash(_("Selecciona una imagen de perfil."), "warning")
            return redirect(url_for("trazas.profile"))

        try:
            _clear_pending_profile_image()
            preview_path = _save_profile_image_preview(form.profile_image.data)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("trazas.profile"))

        session[_PROFILE_IMAGE_SESSION_KEY] = preview_path
        confirm_form = ProfileImageConfirmForm()
        return render_template(
            "profile_image_confirm.html",
            confirm_form=confirm_form,
            preview_url=_profile_image_url(preview_path),
        )

    @bp.route("/perfil/imagen/confirmar", methods=["POST"])
    @login_required
    def profile_image_confirm():
        """Guarda la imagen temporal como imagen de perfil definitiva."""
        form = ProfileImageConfirmForm()
        if not form.validate_on_submit():
            flash(_("No se ha podido confirmar la imagen de perfil."), "error")
            return redirect(url_for("trazas.profile"))

        preview_path = session.pop(_PROFILE_IMAGE_SESSION_KEY, None)
        preview_absolute_path = _profile_image_abspath(preview_path)
        if not preview_path or not preview_absolute_path or not os.path.exists(preview_absolute_path):
            flash(_("No hay ninguna imagen de perfil pendiente de confirmar."), "warning")
            return redirect(url_for("trazas.profile"))

        final_path = _final_profile_image_path(current_user.usuario_id)
        final_absolute_path = _profile_image_abspath(final_path)
        if final_absolute_path is None:
            _delete_profile_image_file(preview_path)
            flash(_("No se ha podido guardar la imagen de perfil."), "error")
            return redirect(url_for("trazas.profile"))

        os.makedirs(os.path.dirname(final_absolute_path), exist_ok=True)
        try:
            os.replace(preview_absolute_path, final_absolute_path)
            current_user.ruta_imagen_perfil = final_path
            db.session.commit()
        except (OSError, SQLAlchemyError):
            db.session.rollback()
            _delete_profile_image_file(preview_path)
            current_app.logger.exception(
                "No se pudo guardar la imagen de perfil del usuario %s.",
                current_user.usuario_id,
            )
            flash(_("No se ha podido guardar la imagen de perfil."), "error")
            return redirect(url_for("trazas.profile"))

        flash(_("Imagen de perfil actualizada correctamente."), "success")
        return redirect(url_for("trazas.profile"))

    @bp.route("/perfil/imagen/cancelar", methods=["POST"])
    @login_required
    def profile_image_cancel():
        """Cancela el cambio de imagen y elimina la previsualización."""
        form = ProfileImageConfirmForm()
        if form.validate_on_submit():
            _clear_pending_profile_image()
            flash(_("Cambio de imagen cancelado."), "info")
        return redirect(url_for("trazas.profile"))

    @bp.route("/perfil/imagenes/<path:filename>")
    @login_required
    def profile_image_file(filename: str):
        """Sirve imágenes de perfil almacenadas en instance/profile_images."""
        absolute_path = _profile_image_abspath(filename)
        if absolute_path is None or not os.path.exists(absolute_path):
            abort(404)

        normalized = filename.replace("\\", "/")
        parts = normalized.split("/")
        if (
            len(parts) >= 3
            and parts[0] == "users"
            and parts[1].isdigit()
            and int(parts[1]) != int(current_user.usuario_id)
            and getattr(current_user, "rol", None) != "admin"
        ):
            abort(403)

        return send_from_directory(_profile_image_storage_root(), normalized)
