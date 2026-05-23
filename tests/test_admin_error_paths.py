"""
===============================================================================
Pruebas de rutas defensivas del panel de administración.

Este módulo cubre ramas defensivas de helpers y endpoints admin sin
modificar la arquitectura existente ni las plantillas.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

import trazasytrazadas.admin as admin_module
from tests.auth_helpers import _create_user, _disable_csrf
from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario


def _login_admin(
    app, client, *, username="admin_paths", email="admin_paths@example.com"
) -> int:
    """Autentica un administrador para la prueba actual."""
    admin_id = _create_user(
        app,
        username=username,
        email=email,
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True
    return admin_id


def test_admin_format_export_pdf_and_flash_helpers(app, monkeypatch):
    """Verifica los formularios en el caso previsto."""
    assert admin_module._format_user_joined_at(None) == "-"
    assert (
        admin_module._format_user_joined_at(datetime(2026, 5, 14, 9, 30))
        == "14/05/2026, 09:30"
    )
    assert (
        admin_module._format_user_joined_at("2026-05-14T09:30:10.123")
        == "14/05/2026, 09:30"
    )
    assert (
        admin_module._format_user_joined_at("2026-05-14 09:30:10")
        == "14/05/2026, 09:30"
    )
    assert (
        admin_module._format_user_joined_at("2026-05-14 09:30")
        == "14/05/2026, 09:30"
    )
    assert admin_module._format_user_joined_at("sin fecha") == "sin fecha"
    assert admin_module._format_model_created_at(None) == "-"

    assert admin_module._parse_positive_int("7", 2) == 7
    assert admin_module._parse_positive_int("0", 2) == 2
    assert admin_module._parse_positive_int("bad", 2) == 2
    assert admin_module._parse_positive_int(None, 2) == 2

    with app.test_request_context("/"):
        assert admin_module._user_role_label("admin") == "Administrador"
        assert admin_module._user_role_label("system") == "Sistema"
        assert admin_module._user_role_label("user") == "Usuario"
        assert admin_module._user_role_label("") == "-"
        assert admin_module._pdf_cell_text("áé🙂")

        user = Usuario(
            usuario_id=1,
            nombre_usuario="UsuarioPdf",
            correo_electronico="pdf@example.com",
            telefono="+34903389323",
            rol="user",
            fecha_alta="2026-05-14 09:30:00",
        )
        rows = admin_module._user_export_rows([user])
        assert rows[1][1] == "UsuarioPdf"
        assert rows[1][3] == "(+34) 903 38 93 23"
        assert admin_module._build_users_pdf([user]).startswith(b"%PDF")

        monkeypatch.setattr(
            admin_module,
            "consume_fold_validation_events",
            lambda: [
                {"status": "success", "fold_name": "modelo-ok"},
                {"status": "error", "fold_name": "modelo-error"},
                {"status": "ignored", "fold_name": "modelo-otro"},
            ],
        )
        admin_module._flash_model_validation_events()


def test_admin_model_validation_background_success_and_failure(
    app, monkeypatch, tmp_path
):
    """Verifica la administración de modelos en el caso previsto."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_path = models_dir / "modelo"
    model_path.write_bytes(b"model")
    app.config["SEG_MODELS_DIR"] = str(models_dir)

    import trazasytrazadas.segmentation_inference as inference_module

    succeeded = {}
    monkeypatch.setattr(
        inference_module,
        "validate_fold_model_file",
        lambda *args, **kwargs: {"kind": "dummy"},
    )
    monkeypatch.setattr(
        admin_module,
        "mark_fold_validation_succeeded",
        lambda fold_name, metadata, models_dir: succeeded.update(
            fold_name=fold_name, metadata=metadata, models_dir=models_dir
        ),
    )

    admin_module._validate_model_file_in_background(
        app, fold_name="modelo", source_filename="modelo.pt"
    )
    assert succeeded["fold_name"] == "modelo"
    assert succeeded["metadata"]["source_filename"] == "modelo.pt"
    assert succeeded["metadata"]["metadata_version"] == 1

    failed = {}
    monkeypatch.setattr(
        inference_module,
        "validate_fold_model_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("modelo inválido")
        ),
    )
    monkeypatch.setattr(
        admin_module,
        "mark_fold_validation_failed",
        lambda fold_name, message, models_dir: failed.update(
            fold_name=fold_name, message=message, models_dir=models_dir
        ),
    )

    admin_module._validate_model_file_in_background(
        app, fold_name="modelo", source_filename=None
    )
    assert failed["fold_name"] == "modelo"
    assert "modelo inválido" in failed["message"]


def test_start_model_validation_task_creates_daemon_thread(app, monkeypatch):
    """Verifica que la gestión de modelos crea el caso previsto."""
    started = []

    class FakeThread:
        def __init__(self, *, target, kwargs, daemon):
            """Inicializa el doble de prueba."""
            self.target = target
            self.kwargs = kwargs
            self.daemon = daemon
            started.append((target, kwargs, daemon))

        def start(self):
            """Registra el inicio del hilo simulado."""
            started.append("started")

    monkeypatch.setattr(admin_module.threading, "Thread", FakeThread)

    with app.app_context():
        admin_module._start_model_validation_task("modelo", "modelo.pt")

    assert started[0][1]["fold_name"] == "modelo"
    assert started[0][1]["source_filename"] == "modelo.pt"
    assert started[0][2] is True
    assert started[1] == "started"


def test_admin_user_index_detail_edit_and_delete_routes(
    app, client, monkeypatch
):
    """Verifica la administración de usuarios en el caso previsto."""
    _disable_csrf(app)
    admin_id = _login_admin(app, client)
    user_id = _create_user(
        app,
        username="UsuarioPaths",
        email="usuario_paths@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )
    other_admin_id = _create_user(
        app,
        username="AdminOtro",
        email="admin_otro@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    system_id = _create_user(
        app,
        username="system_paths",
        email="system_paths@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="system",
    )

    response = client.get("/admin/usuarios/?q=paths&page=99&per_page=999")
    assert response.status_code == 200

    assert client.get("/admin/usuarios/999999").status_code == 404
    assert client.get(f"/admin/usuarios/{system_id}/editar").status_code == 302

    response = client.post(
        f"/admin/usuarios/{other_admin_id}/editar",
        data={
            "nombre_usuario": "AdminOtro",
            "correo_electronico": "admin_otro@example.com",
            "telefono": "",
            "rol": "user",
        },
    )
    assert response.status_code == 302

    def broken_commit():
        """Simula un fallo durante el commit."""
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(db.session, "commit", broken_commit)
    response = client.post(
        f"/admin/usuarios/{user_id}/editar",
        data={
            "nombre_usuario": "UsuarioPaths2",
            "correo_electronico": "usuario_paths2@example.com",
            "telefono": "",
            "rol": "user",
        },
    )
    assert response.status_code == 200

    assert (
        client.post(f"/admin/usuarios/{system_id}/eliminar").status_code == 302
    )
    assert (
        client.post(f"/admin/usuarios/{admin_id}/eliminar").status_code == 302
    )
    assert (
        client.post(f"/admin/usuarios/{other_admin_id}/eliminar").status_code
        == 302
    )


def test_admin_user_delete_rolls_back_and_restores_staged_dirs(
    app, client, monkeypatch
):
    """Verifica la administración de usuarios en el caso previsto."""
    _disable_csrf(app)
    _login_admin(
        app,
        client,
        username="admin_delete_paths",
        email="admin_delete_paths@example.com",
    )
    user_id = _create_user(
        app,
        username="UsuarioDeletePaths",
        email="usuario_delete_paths@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    restored = {}
    purged = {}
    monkeypatch.setattr(
        admin_module,
        "stage_parcel_dirs_for_delete",
        lambda parcel_ids: [("a", "b")],
    )
    monkeypatch.setattr(
        admin_module,
        "restore_staged_parcel_dirs",
        lambda staged: restored.update(staged=staged),
    )
    monkeypatch.setattr(
        admin_module,
        "purge_staged_parcel_dirs",
        lambda staged: purged.update(staged=staged),
    )
    monkeypatch.setattr(
        db.session,
        "commit",
        lambda: (_ for _ in ()).throw(SQLAlchemyError("db down")),
    )

    response = client.post(f"/admin/usuarios/{user_id}/eliminar")
    assert response.status_code == 302
    assert restored == {"staged": [("a", "b")]}
    assert purged == {}


def test_admin_folds_error_branches(app, client, monkeypatch):
    """Verifica la administración de modelos en el caso previsto."""
    _disable_csrf(app)
    _login_admin(
        app,
        client,
        username="admin_folds_paths",
        email="admin_folds_paths@example.com",
    )

    monkeypatch.setattr(
        admin_module,
        "set_active_fold_name",
        lambda name: (_ for _ in ()).throw(ValueError("bad")),
    )
    assert (
        client.post(
            "/admin/folds/activar", data={"fold_name": "bad"}
        ).status_code
        == 302
    )

    monkeypatch.setattr(
        admin_module,
        "set_active_fold_name",
        lambda name: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    assert (
        client.post(
            "/admin/folds/activar", data={"fold_name": "missing"}
        ).status_code
        == 302
    )

    assert client.post("/admin/folds/renombrar", data={}).status_code == 302

    for exc in (
        ValueError("bad"),
        FileNotFoundError("missing"),
        FileExistsError("exists"),
        OSError("disk"),
    ):
        monkeypatch.setattr(
            admin_module,
            "rename_fold_file",
            lambda **kwargs: (_ for _ in ()).throw(exc),
        )
        response = client.post(
            "/admin/folds/renombrar",
            data={"current_name": "modelo-a", "new_name": "modelo-b"},
        )
        assert response.status_code == 302

    app.config["MODEL_UPLOAD_MAX_CONTENT_LENGTH"] = 1
    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "modelo-grande",
            "model_file": (BytesIO(b"abc"), "modelo.pt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302

    app.config["MODEL_UPLOAD_MAX_CONTENT_LENGTH"] = 1024 * 1024
    assert client.post("/admin/folds/subir", data={}).status_code == 302

    for exc in (ValueError("bad"), FileExistsError("exists"), OSError("disk")):
        monkeypatch.setattr(
            admin_module,
            "add_fold_file",
            lambda **kwargs: (_ for _ in ()).throw(exc),
        )
        response = client.post(
            "/admin/folds/subir",
            data={
                "fold_name": "modelo-upload",
                "model_file": (BytesIO(b"abc"), "modelo.pt"),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 302

    for exc in (
        ValueError("bad"),
        FileNotFoundError("missing"),
        OSError("disk"),
    ):
        monkeypatch.setattr(
            admin_module,
            "delete_fold_file",
            lambda fold_name: (_ for _ in ()).throw(exc),
        )
        response = client.post(
            "/admin/folds/eliminar", data={"fold_name": "modelo"}
        )
        assert response.status_code == 302
