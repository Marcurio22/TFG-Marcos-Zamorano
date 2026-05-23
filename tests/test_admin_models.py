"""
===============================================================================
Pruebas de administración de modelos.

Este módulo verifica la gestión administrativa de modelos heredada de la lógica
de folds: listado, subida, activación, renombrado, validación y borrado.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from werkzeug.security import generate_password_hash

import trazasytrazadas.admin as admin_module
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
    assert "Modelo añadido correctamente." in html
    assert "modelo nuevo" in html
    assert "Pendiente" in html

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "modelo nuevo").exists()
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo nuevo")
        ).scalar_one()
        assert model.validacion == "pendiente"


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
    assert "Modelo añadido correctamente." in response.get_data(as_text=True)

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "modelo pendiente").exists()
        assert not list(models_dir.glob("*.upload"))
        assert not list(models_dir.glob(".*.upload"))
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "modelo pendiente")
        ).scalar_one()
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
    assert "Modelo añadido correctamente." in html
    assert "torchscript infer" in html

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "torchscript infer").exists()
        model = db.session.execute(
            db.select(Modelo).where(
                Modelo.nombre_modelo == "torchscript infer"
            )
        ).scalar_one()
        assert model.validacion == "pendiente"


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
