"""Pruebas de administración de modelos.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

import trazasytrazadas.admin as admin_module
import trazasytrazadas.model_store as model_store
from trazasytrazadas.db import db
from trazasytrazadas.models import Modelo
from tests.auth_helpers import (
    _create_user,
    _disable_csrf,
    _serialized_dummy_model,
    _serialized_dummy_torchscript_model,
)


def test_admin_folds_page_lists_models_with_any_safe_name(app, client):
    """La gestión de modelos lista ficheros reales con nombres libres."""
    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = app.config["SEG_MODELS_DIR"]
        Path(models_dir, "fold.0").write_text("a", encoding="utf-8")
        Path(models_dir, "fold.1").write_text("b", encoding="utf-8")
        Path(models_dir, "fold.9").write_text("c", encoding="utf-8")
        Path(models_dir, "modelo principal").write_text("d", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "fold.0" in html
    assert "fold.1" in html
    assert "fold.9" in html
    assert "modelo principal" in html
    assert "fold.10" not in html


def test_admin_folds_page_marks_fold_zero_as_default_active(app, client):
    """Si no hay setting persistido, fold.0 actúa como activo por defecto."""
    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("a", encoding="utf-8")
        (models_dir / "fold.1").write_text("b", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Activo: fold.0" in html


def test_admin_folds_page_prepares_ajax_upload_progress(app, client):
    """La pantalla prepara progreso AJAX para subir modelos."""
    admin_id = _create_user(
        app,
        username="admin_ajax_upload_page",
        email="admin_ajax_upload_page@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("a", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "window.ADMIN_FOLDS_APP" in html
    assert "admin_folds.js" in html
    assert "data-model-upload-progress" in html
    assert "data-upload-warning" in html
    assert "No abandones esta página" in html
    assert "data-upload-cancel-button" in html
    assert "Cancelar subida" in html
    assert "Cancelando subida..." in html
    assert "data-upload-toast-container" in html
    assert "toast toast-top toast-center" in html
    assert "mt-20" in html
    assert "La subida se ha cancelado correctamente." in html
    assert "data-model-table-body" in html
    assert "uploading-model-row-template" in html
    assert "Subiendo {percent}" not in html


def test_admin_folds_javascript_supports_upload_cancellation():
    """El script de modelos puede abortar una subida AJAX en curso."""
    script_path = (
        Path(__file__).resolve().parents[1]
        / "webapp"
        / "trazasytrazadas"
        / "static"
        / "js"
        / "admin_folds.js"
    )

    script = script_path.read_text(encoding="utf-8")

    assert "data-upload-cancel-button" in script
    assert "activeUploadXhr.abort()" in script
    assert "setupCancelUploadButton" in script
    assert "handleUploadCancellation" in script
    assert "hideProgressUi" in script
    assert "showCancellationToast" in script
    assert "dismissToast" in script
    assert "makeCloseIcon" in script
    assert "alert alert-info shadow-lg pointer-events-auto" in script
    assert "data-upload-toast-container" in script
    assert "window.setTimeout(() =>" in script
    assert "}, 5000)" in script


def test_admin_can_activate_fold_and_persists_in_db(app, client):
    """El administrador puede activar un fold y se persiste en SQLite."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("a", encoding="utf-8")
        (models_dir / "fold.1").write_text("b", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/activar",
        data={"fold_name": "fold.1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Modelo activo actualizado correctamente." in response.get_data(
        as_text=True
    )

    with app.app_context():
        active_model = db.session.execute(
            db.select(Modelo).where(Modelo.estado == "activo")
        ).scalar_one()

        assert active_model.nombre_modelo == "fold.1"


def test_admin_can_rename_active_model_with_custom_name(app, client):
    """Renombrar el modelo activo permite nombres libres y actualiza la BD."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.3").write_text("x", encoding="utf-8")
        db.session.add(
            Modelo(
                nombre_modelo="fold.3",
                estado="activo",
                validacion="validado",
            )
        )
        db.session.commit()

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/renombrar",
        data={
            "current_name": "fold.3",
            "new_name": "modelo principal",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Modelo renombrado correctamente." in html

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "modelo principal").exists()
        assert not (models_dir / "fold.3").exists()

        active_model = db.session.execute(
            db.select(Modelo).where(Modelo.estado == "activo")
        ).scalar_one()

        assert active_model.nombre_modelo == "modelo principal"


def test_admin_can_upload_model_as_pending(app, client, monkeypatch):
    """El administrador sube un modelo y queda pendiente de validación."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_upload_fold",
        email="admin_upload_fold@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        lambda fold_name, source_filename: None,
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "modelo nuevo",
            "model_file": (
                BytesIO(_serialized_dummy_model()),
                "modelo-validado.pkl",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Modelo recibido." in html
    assert "modelo nuevo" in html
    assert "Subiendo..." in html
    assert "Pendiente" in html
    assert '"hasRefreshingModels":true' in html.replace(" ", "")

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "modelo nuevo").exists()
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo nuevo")
        ).scalar_one()
        assert model.estado == "subiendo"
        assert model.validacion == "pendiente"


def test_admin_upload_returns_json_for_ajax_request(
    app,
    client,
    monkeypatch,
):
    """La subida AJAX responde JSON sin recargar la página."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_ajax_upload",
        email="admin_ajax_upload@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        lambda fold_name, source_filename: None,
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "modelo ajax",
            "model_file": (
                BytesIO(_serialized_dummy_model()),
                "modelo-ajax.pkl",
            ),
        },
        content_type="multipart/form-data",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["model_name"] == "modelo ajax"
    assert payload["redirect_url"].endswith("/admin/folds/")

    with app.app_context():
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo ajax")
        ).scalar_one()
        assert model.estado == "subiendo"
        assert model.validacion == "pendiente"


def test_admin_upload_requires_valid_csrf(app, client, monkeypatch):
    """La subida de modelos no guarda nada sin CSRF válido."""
    app.config["WTF_CSRF_ENABLED"] = True

    admin_id = _create_user(
        app,
        username="admin_upload_no_csrf",
        email="admin_upload_no_csrf@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    def fail_if_validation_starts(fold_name, source_filename):
        raise AssertionError(
            "No debería arrancar la validación sin CSRF válido."
        )

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        fail_if_validation_starts,
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "modelo sin csrf",
            "model_file": (
                BytesIO(_serialized_dummy_model()),
                "modelo-validado.pkl",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code in {200, 400, 403}

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert not (models_dir / "modelo sin csrf").exists()

        model = db.session.execute(
            db.select(Modelo).where(
                Modelo.nombre_modelo == "modelo sin csrf"
            )
        ).scalar_one_or_none()
        assert model is None


def test_admin_upload_stores_invalid_model_as_pending(
    app, client, monkeypatch
):
    """La validación queda diferida, por lo que el
    archivo se guarda pendiente."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_bad_fold",
        email="admin_bad_fold@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        lambda fold_name, source_filename: None,
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "modelo pendiente",
            "model_file": (
                BytesIO(b"%PDF-1.4\nesto no es un modelo"),
                "falso.pdf",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Modelo recibido." in response.get_data(as_text=True)

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "modelo pendiente").exists()
        assert not list(models_dir.glob("*.upload"))
        assert not list(models_dir.glob(".*.upload"))
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo pendiente")
        ).scalar_one()
        assert model.estado == "subiendo"
        assert model.validacion == "pendiente"


def test_admin_upload_rejects_existing_fold_name(app, client):
    """La subida de folds no sobreescribe modelos ya existentes."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_existing_fold",
        email="admin_existing_fold@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.5").write_text("modelo original", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "fold.5",
            "model_file": (
                BytesIO(_serialized_dummy_model()),
                "modelo-validado.pkl",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ya existe otro modelo con ese nombre." in response.get_data(
        as_text=True
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "fold.5").read_text(
            encoding="utf-8"
        ) == "modelo original"


def test_admin_can_upload_torchscript_infer_model_as_pending(
    app, client, monkeypatch
):
    """La subida de TorchScript queda registrada como pendiente."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_upload_torchscript",
        email="admin_upload_torchscript@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    monkeypatch.setattr(
        admin_module,
        "_start_model_validation_task",
        lambda fold_name, source_filename: None,
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/subir",
        data={
            "fold_name": "torchscript infer",
            "model_file": (
                BytesIO(_serialized_dummy_torchscript_model()),
                "modelo_infer.pt",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Modelo recibido." in html
    assert "torchscript infer" in html
    assert "Subiendo..." in html

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "torchscript infer").exists()
        model = db.session.execute(
            db.select(Modelo).where(
                Modelo.nombre_modelo == "torchscript infer"
            )
        ).scalar_one()
        assert model.estado == "subiendo"
        assert model.validacion == "pendiente"


def test_admin_folds_page_reports_failed_pending_upload(app, client):
    """La pantalla muestra el fallo automático y retira el modelo."""
    admin_id = _create_user(
        app,
        username="admin_failed_pending_model",
        email="admin_failed_pending_model@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        (models_dir / "modelo fallido").write_bytes(b"bad")
        db.session.add(
            Modelo(
                nombre_modelo="modelo fallido",
                estado="subiendo",
                validacion="pendiente",
            )
        )
        db.session.commit()

        model_store.mark_fold_validation_failed(
            "modelo fallido",
            "boom",
            models_dir=models_dir,
        )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ha fallado y se ha eliminado" in html
    assert 'data-model-name="modelo fallido"' not in html
    assert '"hasRefreshingModels":false' in html.replace(" ", "")

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert not (models_dir / "modelo fallido").exists()
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo fallido")
        ).scalar_one_or_none()
        assert model is None


def test_admin_can_delete_non_active_fold(app, client):
    """El administrador puede eliminar un fold si no es el activo."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_delete_fold",
        email="admin_delete_fold@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("activo", encoding="utf-8")
        (models_dir / "fold.1").write_text("borrar", encoding="utf-8")
        (models_dir / ".fold.1.metadata.json").write_text(
            '{"loader_kind": "pickle"}',
            encoding="utf-8",
        )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/eliminar",
        data={"fold_name": "fold.1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Modelo eliminado correctamente." in response.get_data(as_text=True)

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert not (models_dir / "fold.1").exists()
        assert not (models_dir / ".fold.1.metadata.json").exists()
        assert (models_dir / "fold.0").exists()


def test_admin_cannot_delete_active_fold(app, client):
    """El administrador no puede dejar sin modelo activo al sistema."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_delete_active_fold",
        email="admin_delete_active_fold@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("activo", encoding="utf-8")
        (models_dir / "fold.1").write_text("otro", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/eliminar",
        data={"fold_name": "fold.0"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "No se puede eliminar el modelo activo." in response.get_data(
        as_text=True
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "fold.0").exists()
