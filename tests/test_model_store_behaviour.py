"""
===============================================================================
Pruebas de comportamiento de gestión de modelos.

Este módulo cubre validaciones, metadatos, eventos y transiciones de estado de
modelos/folds no cubiertas por los tests funcionales del panel admin.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trazasytrazadas.db import db
from trazasytrazadas.models import Modelo
from trazasytrazadas import model_store


class DummyStorage:
    """FileStorage mínimo para probar add_fold_file."""

    def __init__(self, data: bytes = b"model", filename: str = "modelo.pt"):
        """Inicializa el doble de prueba."""
        self.data = data
        self.filename = filename

    def save(self, destination):
        """Ejecuta un doble auxiliar usado por la prueba."""
        Path(destination).write_bytes(self.data)


def test_get_models_dir_requires_context_without_explicit_path():
    """Verifica que la gestión de modelos exige el caso previsto."""
    with pytest.raises(RuntimeError):
        model_store._get_models_dir()


def test_validation_events_ignore_empty_invalid_and_corrupt_lines(tmp_path):
    """Verifica las validaciones en el caso previsto."""
    model_store.record_fold_validation_event(
        "", "success", models_dir=tmp_path
    )
    model_store.record_fold_validation_event(
        "modelo", "ignored", models_dir=tmp_path
    )
    assert (
        model_store.consume_fold_validation_events(models_dir=tmp_path) == []
    )

    events_path = tmp_path / ".validation_events.jsonl"
    events_path.write_text(
        "not-json\n"
        + json.dumps({"status": "pending", "fold_name": "x"})
        + "\n"
        + json.dumps({"status": "success", "fold_name": "ok"})
        + "\n",
        encoding="utf-8",
    )

    assert model_store.consume_fold_validation_events(models_dir=tmp_path) == [
        {"status": "success", "fold_name": "ok"}
    ]
    assert not events_path.exists()


def test_fold_name_validation_and_legacy_index_parsing():
    """Verifica la gestión de modelos en el caso previsto."""
    assert not model_store.is_valid_fold_name("")
    assert not model_store.is_valid_fold_name(".")
    assert not model_store.is_valid_fold_name("..")
    assert not model_store.is_valid_fold_name(".hidden")
    assert not model_store.is_valid_fold_name("a" * 101)
    assert not model_store.is_valid_fold_name("dir/modelo")
    assert not model_store.is_valid_fold_name("dir\\modelo")
    assert not model_store.is_valid_fold_name("bad:name")
    assert model_store.is_valid_fold_name("modelo-seguro_1.pt")

    assert model_store.parse_fold_index_from_name("fold.12") == 12
    assert model_store.parse_fold_index_from_name("modelo") is None


def test_metadata_read_write_delete_and_invalid_payloads(tmp_path):
    """Verifica el borrado en el caso previsto."""
    with pytest.raises(ValueError):
        model_store.write_fold_metadata("../bad", {}, models_dir=tmp_path)

    assert model_store.read_fold_metadata("../bad", models_dir=tmp_path) == {}
    assert model_store.read_fold_metadata("modelo", models_dir=tmp_path) == {}

    model_store.write_fold_metadata(
        "modelo", {"loader_kind": "auto"}, models_dir=tmp_path
    )
    assert model_store.read_fold_metadata("modelo", models_dir=tmp_path) == {
        "loader_kind": "auto"
    }

    (tmp_path / ".modelo.metadata.json").write_text(
        "not-json", encoding="utf-8"
    )
    assert model_store.read_fold_metadata("modelo", models_dir=tmp_path) == {}

    (tmp_path / ".modelo.metadata.json").write_text("[]", encoding="utf-8")
    assert model_store.read_fold_metadata("modelo", models_dir=tmp_path) == {}

    model_store.delete_fold_metadata("modelo", models_dir=tmp_path)
    model_store.delete_fold_metadata("modelo", models_dir=tmp_path)
    assert not (tmp_path / ".modelo.metadata.json").exists()


def test_list_fold_files_filters_and_sorts(tmp_path):
    """Verifica la gestión de modelos en el caso previsto."""
    (tmp_path / "fold.10").write_bytes(b"x")
    (tmp_path / "fold.2").write_bytes(b"x")
    (tmp_path / "zeta").write_bytes(b"x")
    (tmp_path / "alpha").write_bytes(b"x")
    (tmp_path / ".hidden").write_bytes(b"x")
    (tmp_path / ".alpha.metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pending.upload").write_bytes(b"x")
    (tmp_path / "folder").mkdir()

    assert [row["name"] for row in model_store.list_fold_files(tmp_path)] == [
        "fold.2",
        "fold.10",
        "alpha",
        "zeta",
    ]


def test_context_free_active_model_resolution(tmp_path):
    """Verifica la gestión de modelos en el caso previsto."""
    assert model_store.get_active_model() is None
    assert model_store.get_active_fold_name(models_dir=tmp_path) == "fold.0"

    (tmp_path / "custom").write_bytes(b"x")
    assert (
        model_store.get_active_fold_name(
            models_dir=tmp_path, default_name="missing"
        )
        == "custom"
    )

    (tmp_path / "fold.0").write_bytes(b"x")
    assert (
        model_store.get_active_fold_name(
            models_dir=tmp_path, default_name="fold.0"
        )
        == "fold.0"
    )


def test_sync_and_active_model_variants(app):
    """Verifica la gestión de modelos en el caso previsto."""
    models_dir = Path(app.config["SEG_MODELS_DIR"])
    (models_dir / "fold.0").write_bytes(b"x")
    (models_dir / "custom").write_bytes(b"x")

    with app.app_context():
        model_store.sync_models_from_files(models_dir=models_dir)
        rows = model_store.list_model_rows(models_dir=models_dir)
        assert [row["name"] for row in rows] == ["fold.0", "custom"]
        assert model_store.get_active_model().nombre_modelo == "fold.0"

        active = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "fold.0")
        ).scalar_one()
        active.estado = "no_activo"
        custom = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "custom")
        ).scalar_one()
        custom.validacion = "pendiente"
        db.session.commit()

        model_store.set_active_fold_name("fold.0", models_dir=models_dir)
        assert (
            model_store.get_active_fold_name(models_dir=models_dir) == "fold.0"
        )

        with pytest.raises(ValueError):
            model_store.set_active_fold_name("bad/name", models_dir=models_dir)
        with pytest.raises(FileNotFoundError):
            model_store.set_active_fold_name("missing", models_dir=models_dir)
        with pytest.raises(ValueError):
            model_store.set_active_fold_name("custom", models_dir=models_dir)


def test_rename_fold_file_errors_metadata_and_missing_model_row(app):
    """Verifica la gestión de modelos en el caso previsto."""
    models_dir = Path(app.config["SEG_MODELS_DIR"])
    (models_dir / "old").write_bytes(b"x")
    (models_dir / "exists").write_bytes(b"x")
    (models_dir / ".old.metadata.json").write_text(
        '{"a": 1}', encoding="utf-8"
    )

    with app.app_context():
        with pytest.raises(ValueError):
            model_store.rename_fold_file("", "new", models_dir=models_dir)
        with pytest.raises(ValueError):
            model_store.rename_fold_file(
                "old", "bad/name", models_dir=models_dir
            )
        with pytest.raises(ValueError):
            model_store.rename_fold_file("old", "old", models_dir=models_dir)
        with pytest.raises(FileNotFoundError):
            model_store.rename_fold_file(
                "missing", "new", models_dir=models_dir
            )
        with pytest.raises(FileExistsError):
            model_store.rename_fold_file(
                "old", "exists", models_dir=models_dir
            )

        db.session.add(
            Modelo(
                nombre_modelo="db-exists",
                estado="no_activo",
                validacion="validado",
            )
        )
        db.session.commit()
        with pytest.raises(FileExistsError):
            model_store.rename_fold_file(
                "old", "db-exists", models_dir=models_dir
            )

        model_store.rename_fold_file("old", "renamed", models_dir=models_dir)
        assert not (models_dir / "old").exists()
        assert (models_dir / "renamed").exists()
        assert (models_dir / ".renamed.metadata.json").exists()
        assert (
            db.session.execute(
                db.select(Modelo).where(Modelo.nombre_modelo == "renamed")
            )
            .scalar_one()
            .validacion
            == "validado"
        )


def test_add_fold_file_validations_metadata_and_cleanup(app):
    """Verifica la gestión de modelos en el caso previsto."""
    models_dir = Path(app.config["SEG_MODELS_DIR"])

    with app.app_context():
        with pytest.raises(ValueError):
            model_store.add_fold_file(
                "bad/name", DummyStorage(), models_dir=models_dir
            )
        with pytest.raises(ValueError):
            model_store.add_fold_file("empty", None, models_dir=models_dir)

        model_store.add_fold_file(
            "exists", DummyStorage(), models_dir=models_dir
        )
        with pytest.raises(FileExistsError):
            model_store.add_fold_file(
                "exists", DummyStorage(), models_dir=models_dir
            )

        db.session.add(
            Modelo(
                nombre_modelo="db-exists",
                estado="no_activo",
                validacion="validado",
            )
        )
        db.session.commit()
        with pytest.raises(FileExistsError):
            model_store.add_fold_file(
                "db-exists", DummyStorage(), models_dir=models_dir
            )

        with pytest.raises(ValueError):
            model_store.add_fold_file(
                "zero", DummyStorage(b""), models_dir=models_dir
            )
        assert not any(
            path.name.endswith(".upload") for path in models_dir.iterdir()
        )

        def validator(path):
            """Valida un archivo de modelo de forma simulada."""
            assert Path(path).read_bytes() == b"model"
            return {"loader_kind": "pickle"}

        final_path = model_store.add_fold_file(
            "validated",
            DummyStorage(filename="source model.pt"),
            validator=validator,
            models_dir=models_dir,
            validation_status="unknown",
        )
        assert final_path.exists()
        assert (
            model_store.read_fold_metadata("validated", models_dir=models_dir)[
                "loader_kind"
            ]
            == "pickle"
        )
        assert (
            model_store.read_fold_metadata("validated", models_dir=models_dir)[
                "source_filename"
            ]
            == "source_model.pt"
        )
        assert (
            db.session.execute(
                db.select(Modelo).where(Modelo.nombre_modelo == "validated")
            )
            .scalar_one()
            .validacion
            == "validado"
        )

        pending_path = model_store.add_fold_file(
            "pending",
            DummyStorage(),
            models_dir=models_dir,
            validation_status="invalid-status",
        )
        assert pending_path.exists()
        assert (
            db.session.execute(
                db.select(Modelo).where(Modelo.nombre_modelo == "pending")
            )
            .scalar_one()
            .validacion
            == "pendiente"
        )


def test_validation_success_and_failure_transitions(app):
    """Verifica las validaciones en el caso previsto."""
    models_dir = Path(app.config["SEG_MODELS_DIR"])
    (models_dir / "pending").write_bytes(b"x")
    model_store.write_fold_metadata(
        "pending", {"old": True}, models_dir=models_dir
    )

    with app.app_context():
        db.session.add(
            Modelo(
                nombre_modelo="pending",
                estado="no_activo",
                validacion="pendiente",
            )
        )
        db.session.commit()

        model_store.mark_fold_validation_succeeded(
            "pending",
            {"loader_kind": "auto"},
            models_dir=models_dir,
        )
        model = db.session.execute(
            db.select(Modelo).where(Modelo.nombre_modelo == "pending")
        ).scalar_one()
        assert model.validacion == "validado"
        assert (
            model_store.read_fold_metadata("pending", models_dir=models_dir)[
                "loader_kind"
            ]
            == "auto"
        )
        events = model_store.consume_fold_validation_events(
            models_dir=models_dir
        )
        assert events[0]["status"] == "success"

        with pytest.raises(ValueError):
            model_store.mark_fold_validation_succeeded(
                "bad/name", models_dir=models_dir
            )

        (models_dir / "bad").write_bytes(b"x")
        model_store.write_fold_metadata(
            "bad", {"loader_kind": "auto"}, models_dir=models_dir
        )
        db.session.add(
            Modelo(
                nombre_modelo="bad", estado="no_activo", validacion="pendiente"
            )
        )
        db.session.commit()

        model_store.mark_fold_validation_failed(
            "bad", "boom", models_dir=models_dir
        )
        assert not (models_dir / "bad").exists()
        assert not (models_dir / ".bad.metadata.json").exists()
        assert (
            db.session.execute(
                db.select(Modelo).where(Modelo.nombre_modelo == "bad")
            ).scalar_one_or_none()
            is None
        )
        assert (
            model_store.consume_fold_validation_events(models_dir=models_dir)[
                0
            ]["status"]
            == "error"
        )

        model_store.mark_fold_validation_failed(
            "bad/name", "ignored", models_dir=models_dir
        )


def test_validation_helpers_without_app_context(tmp_path):
    """Verifica las validaciones en el caso previsto."""
    (tmp_path / "orphan").write_bytes(b"x")
    model_store.mark_fold_validation_succeeded(
        "orphan", {"a": 1}, models_dir=tmp_path
    )
    assert model_store.read_fold_metadata("orphan", models_dir=tmp_path) == {
        "a": 1
    }

    model_store.mark_fold_validation_failed(
        "orphan", "boom", models_dir=tmp_path
    )
    assert not (tmp_path / "orphan").exists()


def test_delete_fold_file_errors_and_success(app):
    """Verifica la gestión de modelos en el caso previsto."""
    models_dir = Path(app.config["SEG_MODELS_DIR"])
    (models_dir / "active").write_bytes(b"x")
    (models_dir / "inactive").write_bytes(b"x")
    model_store.write_fold_metadata(
        "inactive", {"a": 1}, models_dir=models_dir
    )

    with app.app_context():
        db.session.add_all(
            [
                Modelo(
                    nombre_modelo="active",
                    estado="activo",
                    validacion="validado",
                ),
                Modelo(
                    nombre_modelo="inactive",
                    estado="no_activo",
                    validacion="validado",
                ),
            ]
        )
        db.session.commit()

        with pytest.raises(ValueError):
            model_store.delete_fold_file("bad/name", models_dir=models_dir)
        with pytest.raises(FileNotFoundError):
            model_store.delete_fold_file("missing", models_dir=models_dir)
        with pytest.raises(ValueError):
            model_store.delete_fold_file("active", models_dir=models_dir)

        model_store.delete_fold_file("inactive", models_dir=models_dir)
        assert not (models_dir / "inactive").exists()
        assert not (models_dir / ".inactive.metadata.json").exists()
        assert (
            db.session.execute(
                db.select(Modelo).where(Modelo.nombre_modelo == "inactive")
            ).scalar_one_or_none()
            is None
        )
